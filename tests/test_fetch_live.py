"""M2 live smoke test: a real CC-licensed SVG download + cache + ledger end-to-end.

Uses the bioicons backend (reachable). The equivalent Zenodo check requires zenodo.org to
be reachable; it is skipped automatically where the host is blocked by network policy.
"""

from __future__ import annotations

import pytest
import requests

from scidraw_agent.backends.bioart import ITEM_PAGE, BioartBackend
from scidraw_agent.backends.bioicons import INDEX_URL, BioiconsBackend
from scidraw_agent.backends.healthicons import INDEX_URL as HI_INDEX
from scidraw_agent.backends.healthicons import HealthIconsBackend
from scidraw_agent.backends.phylopic import ROOT as PP_ROOT
from scidraw_agent.backends.phylopic import PhylopicBackend
from scidraw_agent.backends.wikimedia import COMMONS_API, WikimediaBackend
from scidraw_agent.backends.zenodo import ZENODO_API, ZenodoBackend
from scidraw_agent.config import Config
from scidraw_agent.fetch import AssetFetcher


def _reachable(url: str) -> bool:
    try:
        return requests.get(url, timeout=10, headers={"User-Agent": "scidraw-agent/0.1"}).ok
    except requests.RequestException:
        return False


@pytest.mark.skipif(not _reachable(INDEX_URL), reason="bioicons host not reachable")
def test_live_bioicons_download(tmp_path):
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[BioiconsBackend()])
    result = fetcher.resolve("neuron")

    assert result.record is not None, "expected at least one CC-licensed neuron asset"
    assert result.record.license  # license captured for the ledger
    body = open(result.record.local_path, "rb").read()
    assert body.lstrip().startswith(b"<") and b"svg" in body[:400].lower()
    assert fetcher.registry.records()  # provenance recorded


@pytest.mark.skipif(not _reachable(ITEM_PAGE.format(id=60)), reason="NIH BIOART host not reachable")
def test_live_bioart_download(tmp_path):
    # Real public-domain vector SVG over the stable file proxy.
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[BioartBackend()])
    result = fetcher.resolve("pyramidal neuron")

    assert result.record is not None, "expected a BIOART neuron asset"
    assert result.record.license == "public-domain"
    body = open(result.record.local_path, "rb").read()
    # BIOART SVGs are namespace-prefixed (<ns0:svg ...>), so match "svg" loosely.
    assert body.lstrip().startswith(b"<") and b"svg" in body[:600].lower()
    assert b"data:image" not in body[:2000].lower()  # vector, not an embedded raster


@pytest.mark.skipif(not _reachable(ZENODO_API), reason="Zenodo host not reachable")
def test_live_zenodo_download(tmp_path):
    # The cloud build sandbox could not reach zenodo.org; verify it works where reachable.
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[ZenodoBackend()])
    result = fetcher.resolve("neuron")

    assert result.record is not None, "expected a CC-BY SciDraw/Zenodo asset"
    assert result.record.license and result.record.doi
    body = open(result.record.local_path, "rb").read()
    assert body.lstrip().startswith(b"<") and b"svg" in body[:400].lower()


@pytest.mark.skipif(not _reachable(COMMONS_API), reason="Wikimedia Commons not reachable")
def test_live_wikimedia_download(tmp_path):
    # Human neuroanatomy SciDraw/BIOART lack; mixed-license -> gate picks a CC-BY/CC0/PD one.
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[WikimediaBackend()])
    result = fetcher.resolve("hippocampus")

    assert result.record is not None, "expected a CC-compatible Commons hippocampus SVG"
    from scidraw_agent.registry import license_ok

    assert license_ok(result.record.license)
    body = open(result.record.local_path, "rb").read()
    assert body.lstrip().startswith(b"<") and b"svg" in body[:600].lower()


@pytest.mark.skipif(not _reachable(HI_INDEX), reason="Health Icons host not reachable")
def test_live_healthicons_download(tmp_path):
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[HealthIconsBackend()])
    result = fetcher.resolve("brain")

    assert result.record is not None and result.record.license == "cc0-1.0"
    body = open(result.record.local_path, "rb").read()
    assert b"svg" in body[:400].lower()


@pytest.mark.skipif(not _reachable(PP_ROOT), reason="PhyloPic API not reachable")
def test_live_phylopic_download(tmp_path):
    # Organism silhouette (taxonomic name) for cohort/study-design panels.
    fetcher = AssetFetcher(Config(cache_dir=tmp_path), backends=[PhylopicBackend()])
    result = fetcher.resolve("mus musculus")

    assert result.record is not None, "expected a PhyloPic mouse silhouette"
    from scidraw_agent.registry import license_ok

    assert license_ok(result.record.license)
    body = open(result.record.local_path, "rb").read()
    assert b"svg" in body[:400].lower()
