"""M2: asset fetcher — mocked Zenodo search/download, license gate, cache hit."""

from __future__ import annotations

import responses

from scidraw_agent.backends.bioart import FILE_API, BioartBackend
from scidraw_agent.backends.healthicons import INDEX_URL as HI_INDEX
from scidraw_agent.backends.healthicons import HealthIconsBackend
from scidraw_agent.backends.phylopic import IMAGES as PP_IMAGES
from scidraw_agent.backends.phylopic import ROOT as PP_ROOT
from scidraw_agent.backends.phylopic import PhylopicBackend
from scidraw_agent.backends.wikimedia import COMMONS_API, WikimediaBackend
from scidraw_agent.backends.zenodo import ZENODO_API, ZenodoBackend
from scidraw_agent.config import Config
from scidraw_agent.fetch import AssetFetcher, HttpClient
from scidraw_agent.registry import license_ok

_BIOART_INDEX = [
    {"id": 60, "file_id": 628024, "title": "Brain Lateral", "keywords": ["brain", "cortex"]},
    {"id": 424, "file_id": 633914, "title": "Pyramidal Neuron", "keywords": ["pyramidal neuron"]},
]


def _zenodo_payload():
    # NC deposit listed first so resolve must reject it before reaching the CC-BY one.
    return {
        "hits": {
            "hits": [
                {
                    "metadata": {
                        "title": "Neuron (NC)",
                        "doi": "10.5281/zenodo.111",
                        "license": {"id": "cc-by-nc-4.0"},
                        "creators": [{"name": "Doe, J."}],
                    },
                    "files": [
                        {"key": "nc.svg", "links": {"self": "https://zenodo.org/files/nc.svg"}}
                    ],
                },
                {
                    "metadata": {
                        "title": "Pyramidal Neuron",
                        "doi": "10.5281/zenodo.222",
                        "license": {"id": "cc-by-4.0"},
                        "creators": [{"name": "Roe, R."}],
                    },
                    "files": [
                        {"key": "n.svg", "links": {"self": "https://zenodo.org/files/n.svg"}}
                    ],
                },
            ]
        }
    }


@responses.activate
def test_resolve_picks_compatible_and_records_ledger(tmp_path):
    responses.add(responses.GET, ZENODO_API, json=_zenodo_payload(), status=200)
    responses.add(responses.GET, "https://zenodo.org/files/n.svg", body=b"<svg/>", status=200)
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])

    result = fetcher.resolve("neuron")
    assert result.record is not None
    assert result.record.license == "cc-by-4.0"
    assert result.record.doi == "10.5281/zenodo.222"
    assert result.record.local_path

    # the CC-BY-NC deposit was flagged/rejected (A6)
    assert any(r.license == "cc-by-nc-4.0" for r in result.rejected)
    # license recorded in the persisted ledger
    assert any(r.doi == "10.5281/zenodo.222" for r in fetcher.registry.records())


@responses.activate
def test_cache_hit_avoids_second_download(tmp_path):
    responses.add(responses.GET, ZENODO_API, json=_zenodo_payload(), status=200)
    responses.add(responses.GET, "https://zenodo.org/files/n.svg", body=b"<svg/>", status=200)
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])

    fetcher.resolve("neuron")
    fetcher.resolve("neuron")

    downloads = [c for c in responses.calls if c.request.url == "https://zenodo.org/files/n.svg"]
    assert len(downloads) == 1


@responses.activate
def test_resolve_returns_none_when_all_incompatible(tmp_path):
    payload = {
        "hits": {
            "hits": [
                {
                    "metadata": {"title": "Neuron (SA)", "license": {"id": "cc-by-sa-4.0"}},
                    "files": [{"key": "a.svg", "links": {"self": "https://zenodo.org/a.svg"}}],
                }
            ]
        }
    }
    responses.add(responses.GET, ZENODO_API, json=payload, status=200)
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])

    result = fetcher.resolve("neuron")
    assert result.record is None
    assert len(result.rejected) == 1


@responses.activate
def test_zenodo_relevance_skips_offtopic_popular_hit(tmp_path):
    # bestmatch can still surface an off-topic deposit first; the title-relevance gate
    # must skip it and pick the deposit that actually matches the query.
    payload = {
        "hits": {
            "hits": [
                {
                    "metadata": {"title": "mouse", "license": {"id": "cc-by-4.0"}},
                    "files": [{"key": "m.svg", "links": {"self": "https://zenodo.org/m.svg"}}],
                },
                {
                    "metadata": {"title": "Pyramidal Neuron", "license": {"id": "cc-by-4.0"}},
                    "files": [{"key": "p.svg", "links": {"self": "https://zenodo.org/p.svg"}}],
                },
            ]
        }
    }
    responses.add(responses.GET, ZENODO_API, json=payload, status=200)
    responses.add(responses.GET, "https://zenodo.org/p.svg", body=b"<svg/>", status=200)
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])

    result = fetcher.resolve("pyramidal neuron")
    assert result.record is not None
    assert result.record.title == "Pyramidal Neuron"  # not "mouse"
    assert all(c.title != "mouse" for c in result.candidates)  # off-topic hit dropped


@responses.activate
def test_zenodo_relevance_returns_none_when_no_title_match(tmp_path):
    # SciDraw lacks the term -> Zenodo returns a generic deposit -> filtered -> no false match.
    payload = {
        "hits": {
            "hits": [
                {
                    "metadata": {"title": "Hepatocyte", "license": {"id": "cc-by-4.0"}},
                    "files": [{"key": "h.svg", "links": {"self": "https://zenodo.org/h.svg"}}],
                }
            ]
        }
    }
    responses.add(responses.GET, ZENODO_API, json=payload, status=200)
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])

    result = fetcher.resolve("thalamus")
    assert result.record is None
    assert result.candidates == []  # off-topic deposit not offered as a candidate


# --------------------------------------------------------------------------- #
# NIH BIOART backend (public-domain human/clinical anatomy)
# --------------------------------------------------------------------------- #
def test_bioart_token_match_builds_proxy_record():
    backend = BioartBackend(index=_BIOART_INDEX)
    # order-independent token match: "brain lateral" / "lateral brain" both hit id 60
    recs = backend.search("lateral brain", 10, http=None)
    assert [r.title for r in recs] == ["Brain Lateral"]
    r = recs[0]
    assert r.source_url == FILE_API.format(id=60, file_id=628024)
    assert r.license == "public-domain" and license_ok(r.license)
    assert r.backend == "bioart" and r.creators


def test_bioart_no_match_returns_empty():
    backend = BioartBackend(index=_BIOART_INDEX)
    assert backend.search("thalamus", 10, http=None) == []  # degrade gracefully -> next backend


def test_bioart_packaged_index_loads_and_matches():
    # The shipped catalog (no injected index) loads and matches a core neuro term.
    recs = BioartBackend().search("brain", 5, http=None)
    assert recs and all(r.license == "public-domain" for r in recs)


def test_bioart_index_covers_neuroimaging_equipment():
    # The expanded index adds neuroimaging hardware (MRI/PET/CT) for the user's domain.
    backend = BioartBackend()
    assert any("Neonatal MRI" in r.title for r in backend.search("neonatal mri", 5, http=None))
    assert backend.search("PET scanner", 5, http=None)
    assert backend.search("CT scanner", 5, http=None)


def test_bioart_index_entries_are_wellformed():
    # Every shipped entry has the fields the backend needs (guards against a bad edit).
    for e in BioartBackend()._load_index():
        assert isinstance(e["id"], int) and isinstance(e["file_id"], int)
        assert e["title"] and isinstance(e.get("keywords", []), list)


@responses.activate
def test_bioart_resolve_downloads_and_records(tmp_path):
    url = FILE_API.format(id=424, file_id=633914)
    responses.add(responses.GET, url, body=b"<svg xmlns='http://www.w3.org/2000/svg'/>", status=200)
    fetcher = AssetFetcher(
        Config(cache_dir=tmp_path),
        backends=[BioartBackend(index=_BIOART_INDEX)],
        http=HttpClient(Config(cache_dir=tmp_path)),
    )
    result = fetcher.resolve("pyramidal neuron")
    assert result.record is not None
    assert result.record.license == "public-domain"
    assert result.record.local_path
    assert any(r.title == "Pyramidal Neuron" for r in fetcher.registry.records())


# --------------------------------------------------------------------------- #
# Wikimedia Commons backend (broad human-neuroanatomy, mixed license -> gated)
# --------------------------------------------------------------------------- #
def _commons_payload():
    return {
        "query": {
            "pages": {
                "10": {
                    "index": 1,
                    "title": "File:Thalamus-schematic.svg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/x/Thalamus-schematic.svg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-SA 3.0"},
                                "Artist": {"value": "<a href='/u'>SA Person</a>"},
                            },
                        }
                    ],
                },
                "11": {
                    "index": 2,
                    "title": "File:Thalamus diagram.png",  # non-svg -> skipped
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/x/Thalamus.png",
                            "extmetadata": {"LicenseShortName": {"value": "CC0"}},
                        }
                    ],
                },
                "12": {
                    "index": 3,
                    "title": "File:ThalamicNuclei.svg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/x/ThalamicNuclei.svg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "Public domain"},
                                "Artist": {"value": "<b>Anatomist</b>"},
                            },
                        }
                    ],
                },
            }
        }
    }


def test_wikimedia_filters_svg_and_normalizes_license():
    import types

    http = types.SimpleNamespace(get_json=lambda url, params=None: _commons_payload())
    recs = WikimediaBackend().search("thalamus", 10, http)
    titles = [r.title for r in recs]
    assert "Thalamus diagram.png" not in titles  # non-svg dropped
    assert titles == ["Thalamus-schematic.svg", "ThalamicNuclei.svg"]  # relevance order
    assert recs[0].license == "cc-by-sa-3.0" and not license_ok(recs[0].license)
    assert recs[1].license == "public-domain" and license_ok(recs[1].license)
    assert recs[1].creators == ["Anatomist"]  # HTML stripped from Artist


@responses.activate
def test_wikimedia_resolve_skips_sa_picks_public_domain(tmp_path):
    responses.add(responses.GET, COMMONS_API, json=_commons_payload(), status=200)
    responses.add(
        responses.GET,
        "https://upload.wikimedia.org/x/ThalamicNuclei.svg",
        body=b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        status=200,
    )
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[WikimediaBackend()])
    result = fetcher.resolve("thalamus")
    assert result.record is not None
    assert result.record.title == "ThalamicNuclei.svg"  # CC-BY-SA one skipped
    assert any("sa" in (r.license or "") for r in result.rejected)


# --------------------------------------------------------------------------- #
# Health Icons backend (CC0)
# --------------------------------------------------------------------------- #
_HI_INDEX = [
    {
        "id": "brain",
        "category": "body",
        "path": "body/neurology",
        "tags": ["Neurology"],
        "title": "Brain",
    },
    {"id": "skull", "category": "body", "path": "body/skull", "tags": ["Skull"], "title": "Skull"},
    {
        "id": "death",
        "category": "symbols",
        "path": "symbols/death",
        "tags": ["Skull", "Death"],
        "title": "Death",
    },
]


def test_healthicons_title_match_ranks_before_tag_match():
    import types

    http = types.SimpleNamespace(get_json=lambda url, params=None: _HI_INDEX)
    backend = HealthIconsBackend()
    recs = backend.search("skull", 5, http)
    assert recs[0].title == "Skull"  # title match beats the tag-only "Death" icon
    assert all(r.license == "cc0-1.0" for r in recs)
    assert recs[0].source_url.endswith("svg/outline/body/skull.svg")


@responses.activate
def test_healthicons_resolve_downloads(tmp_path):
    responses.add(responses.GET, HI_INDEX, json=_HI_INDEX, status=200)
    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/resolvetosavelives/healthicons/main/"
        "public/icons/svg/outline/body/neurology.svg",
        body=b"<svg/>",
        status=200,
    )
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[HealthIconsBackend()])
    result = fetcher.resolve("brain")
    assert result.record is not None and result.record.license == "cc0-1.0"
    assert result.record.local_path


# --------------------------------------------------------------------------- #
# PhyloPic backend (organism silhouettes; per-image license)
# --------------------------------------------------------------------------- #
def _pp_images():
    return {
        "_embedded": {
            "items": [
                {
                    "attribution": "NC Artist",
                    "_links": {
                        "license": {"href": "https://creativecommons.org/licenses/by-nc/4.0/"},
                        "vectorFile": {"href": "https://images.phylopic.org/a/vector.svg"},
                        "specificNode": {"title": "Mus musculus"},
                    },
                },
                {
                    "attribution": "PD Artist",
                    "_links": {
                        "license": {"href": "https://creativecommons.org/publicdomain/zero/1.0/"},
                        "vectorFile": {"href": "https://images.phylopic.org/b/vector.svg"},
                        "specificNode": {"title": "Mus musculus"},
                    },
                },
            ]
        }
    }


def test_phylopic_maps_licenses():
    import types

    def _get(url, params=None):
        return {"build": 541} if url == PP_ROOT else _pp_images()

    http = types.SimpleNamespace(get_json=_get)
    recs = PhylopicBackend().search("mus musculus", 5, http)
    assert [r.license for r in recs] == ["cc-by-nc", "cc0-1.0"]
    assert not license_ok(recs[0].license) and license_ok(recs[1].license)
    assert recs[1].title == "Mus musculus" and recs[1].creators == ["PD Artist"]


@responses.activate
def test_phylopic_resolve_skips_nc_picks_cc0(tmp_path):
    responses.add(responses.GET, PP_ROOT, json={"build": 541}, status=200)
    responses.add(responses.GET, PP_IMAGES, json=_pp_images(), status=200)
    responses.add(
        responses.GET, "https://images.phylopic.org/b/vector.svg", body=b"<svg/>", status=200
    )
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[PhylopicBackend()])
    result = fetcher.resolve("mus musculus")
    assert result.record is not None and result.record.license == "cc0-1.0"
    assert any("nc" in (r.license or "") for r in result.rejected)
