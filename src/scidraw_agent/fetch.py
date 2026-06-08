"""Multi-backend asset retrieval behind one interface, with HTTP retry + caching.

`AssetFetcher.resolve(query)` searches each backend in priority order (SciDraw/Zenodo
first, bioicons fallback), skips license-incompatible candidates (recording them as
rejected for A6), then downloads + caches the first compatible asset and records it in the
license/DOI ledger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import requests

from .config import Config, load_config
from .models import AssetRecord
from .registry import Registry

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    """requests.Session wrapper with a real User-Agent and exponential-backoff retry."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.config.user_agent

    def _request(self, url: str, *, params: dict | None = None) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.config.http_max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.config.http_timeout)
                if resp.status_code in _RETRYABLE_STATUS:
                    raise requests.HTTPError(f"retryable status {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                # 4xx other than the retryable set should fail fast.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in _RETRYABLE_STATUS:
                    raise
                last_exc = exc
                if attempt < self.config.http_max_retries:
                    time.sleep(2 ** (attempt + 1))
        raise last_exc  # type: ignore[misc]

    def get_json(self, url: str, *, params: dict | None = None) -> dict:
        return self._request(url, params=params).json()

    def get_bytes(self, url: str) -> bytes:
        return self._request(url).content


@runtime_checkable
class AssetBackend(Protocol):
    """A source of organic SVG assets. Implementations return un-downloaded candidates."""

    name: str

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]: ...


@dataclass
class ResolveResult:
    record: AssetRecord | None
    candidates: list[AssetRecord] = field(default_factory=list)
    rejected: list[AssetRecord] = field(default_factory=list)


def default_backends() -> list[AssetBackend]:
    # Local import avoids a circular import (backends type-only-reference HttpClient).
    # Priority (curated first, broad gap-fillers after):
    #   SciDraw/Zenodo  primary, rodent/systems-neuro (CC-BY)
    #   NIH BIOART      curated public-domain human/clinical anatomy + imaging hardware
    #   bioicons        curated CC science icons
    #   Wikimedia       broad human-neuroanatomy gap-filler (per-file license gate)
    #   Health Icons    CC0 medical line icons
    #   PhyloPic        organism silhouettes (cohort/study-design panels)
    from .backends.bioart import BioartBackend
    from .backends.bioicons import BioiconsBackend
    from .backends.healthicons import HealthIconsBackend
    from .backends.phylopic import PhylopicBackend
    from .backends.wikimedia import WikimediaBackend
    from .backends.zenodo import ZenodoBackend

    return [
        ZenodoBackend(),
        BioartBackend(),
        BioiconsBackend(),
        WikimediaBackend(),
        HealthIconsBackend(),
        PhylopicBackend(),
    ]


class AssetFetcher:
    """Searches backends, applies the license gate, downloads + caches via the Registry."""

    def __init__(
        self,
        config: Config | None = None,
        *,
        backends: list[AssetBackend] | None = None,
        registry: Registry | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.config = config or load_config()
        self.http = http or HttpClient(self.config)
        self.registry = registry or Registry(self.config)
        self.backends = backends if backends is not None else default_backends()

    def search(self, term: str, size: int = 10) -> list[AssetRecord]:
        results: list[AssetRecord] = []
        for backend in self.backends:
            try:
                results.extend(backend.search(term, size, self.http))
            except Exception:  # a failing backend must not break the others
                continue
        return results

    def resolve(self, query: str, size: int = 10) -> ResolveResult:
        """Return the first license-compatible, downloaded asset for ``query``."""
        candidates = self.search(query, size)
        rejected: list[AssetRecord] = []
        for cand in candidates:
            if not self.registry.license_ok(cand.license):
                rejected.append(cand)
                continue
            record = self.registry.get_or_download(cand, self.http.get_bytes)
            return ResolveResult(record=record, candidates=candidates, rejected=rejected)
        return ResolveResult(record=None, candidates=candidates, rejected=rejected)
