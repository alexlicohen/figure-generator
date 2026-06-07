"""Local asset cache + DOI/license ledger with the CC-compatibility gate (A6).

The ledger records every imported asset's DOI + license for the figure legend, and the
license gate BLOCKS/flags anything not CC-BY-compatible (rejects NC/ND/SA and unknown
licenses) before it can be embedded.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from .config import Config, load_config
from .models import AssetRecord

# Permissive code-style licenses that are commercial-use + redistribution compatible.
_PERMISSIVE = {"mit", "bsd", "isc", "zlib", "apache", "apache-2.0", "bsd-3-clause", "bsd-2-clause"}

# Substrings that make a license incompatible with freely reusable figures.
_INCOMPATIBLE_MARKERS = ("-nc", "-nd", "-sa", "noncommercial", "noderiv", "sharealike")


def license_ok(license_id: str | None) -> bool:
    """True if the license permits commercial reuse + redistribution with attribution.

    Accepts CC-BY (any version), CC0/public-domain, and common permissive licenses.
    Rejects CC-BY-NC / -ND / -SA and unknown/missing licenses (flagged, not embedded).
    """
    if not license_id:
        return False
    lic = license_id.strip().lower()
    if any(marker in lic for marker in _INCOMPATIBLE_MARKERS):
        return False
    if lic.startswith(("cc-by", "cc0", "cc-0")):
        return True
    if "public" in lic or "pddl" in lic or "zero" in lic:
        return True
    return lic in _PERMISSIVE


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "asset"


class Registry:
    """SVG cache + license/DOI ledger persisted as JSON in the cache dir."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.config.ensure_dirs()
        self._ledger: dict[str, AssetRecord] = {}
        self._load()

    # -- license gate ------------------------------------------------------ #
    @staticmethod
    def license_ok(license_id: str | None) -> bool:
        return license_ok(license_id)

    # -- cache + download -------------------------------------------------- #
    def cache_path(self, record: AssetRecord) -> Path:
        key = record.doi or record.source_url or record.title
        digest = hashlib.sha1(key.encode()).hexdigest()[:8]
        return self.config.assets_dir / f"{_slug(record.title)}-{digest}.svg"

    def get_or_download(
        self, record: AssetRecord, downloader: Callable[[str], bytes]
    ) -> AssetRecord:
        """Return ``record`` with a cached local SVG, downloading only on a cache miss."""
        path = self.cache_path(record)
        if not path.exists():
            if not record.source_url:
                raise ValueError("AssetRecord has no source_url to download from.")
            path.write_bytes(downloader(record.source_url))
        record.local_path = str(path)
        self._add(record)
        return record

    # -- ledger ------------------------------------------------------------ #
    def _ledger_key(self, record: AssetRecord) -> str:
        return record.doi or record.source_url or record.local_path or record.title

    def _add(self, record: AssetRecord) -> None:
        self._ledger[self._ledger_key(record)] = record
        self._save()

    def records(self) -> list[AssetRecord]:
        return list(self._ledger.values())

    def _load(self) -> None:
        path = self.config.ledger_path
        if path.exists():
            raw = json.loads(path.read_text())
            self._ledger = {k: AssetRecord.model_validate(v) for k, v in raw.items()}

    def _save(self) -> None:
        self.config.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.model_dump() for k, v in self._ledger.items()}
        self.config.ledger_path.write_text(json.dumps(data, indent=2))
