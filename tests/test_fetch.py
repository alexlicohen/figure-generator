"""M2: asset fetcher — mocked Zenodo search/download, license gate, cache hit."""

from __future__ import annotations

import responses

from scidraw_agent.backends.bioart import FILE_API, BioartBackend
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
                    "metadata": {"title": "SA", "license": {"id": "cc-by-sa-4.0"}},
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
