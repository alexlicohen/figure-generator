"""M2 live smoke test: a real CC-licensed SVG download + cache + ledger end-to-end.

Uses the bioicons backend (reachable). The equivalent Zenodo check requires zenodo.org to
be reachable; it is skipped automatically where the host is blocked by network policy.
"""

from __future__ import annotations

import pytest
import requests

from scidraw_agent.backends.bioicons import INDEX_URL, BioiconsBackend
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
