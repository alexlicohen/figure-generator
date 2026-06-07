"""M2: license gate + cache/ledger registry."""

from __future__ import annotations

from scidraw_agent.config import Config
from scidraw_agent.models import AssetRecord
from scidraw_agent.registry import Registry, license_ok


def test_license_gate_accepts_compatible():
    assert license_ok("cc-by-4.0")
    assert license_ok("CC-BY-3.0")
    assert license_ok("cc0-1.0")
    assert license_ok("cc-0")
    assert license_ok("mit")
    assert license_ok("public-domain")


def test_license_gate_rejects_incompatible_and_unknown():
    assert not license_ok("cc-by-nc-4.0")
    assert not license_ok("cc-by-sa-4.0")
    assert not license_ok("cc-by-nd-4.0")
    assert not license_ok(None)
    assert not license_ok("")
    assert not license_ok("proprietary")


def test_registry_caches_and_writes_ledger(tmp_path):
    cfg = Config(cache_dir=tmp_path)
    reg = Registry(cfg)
    rec = AssetRecord(
        query="neuron",
        title="Pyramidal Neuron",
        backend="bioicons",
        license="cc0-1.0",
        source_url="https://example.org/neuron.svg",
    )
    calls = {"n": 0}

    def fake_download(url: str) -> bytes:
        calls["n"] += 1
        return b"<svg/>"

    out = reg.get_or_download(rec, fake_download)
    assert out.local_path and out.local_path.endswith(".svg")
    assert calls["n"] == 1

    # second resolve of the same asset hits the cache, no re-download
    reg.get_or_download(rec, fake_download)
    assert calls["n"] == 1

    # ledger persisted and reloads
    reg2 = Registry(cfg)
    records = reg2.records()
    assert len(records) == 1
    assert records[0].license == "cc0-1.0"
