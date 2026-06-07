"""M2: asset fetcher — mocked Zenodo search/download, license gate, cache hit."""

from __future__ import annotations

import responses

from scidraw_agent.backends.zenodo import ZENODO_API, ZenodoBackend
from scidraw_agent.config import Config
from scidraw_agent.fetch import AssetFetcher


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
