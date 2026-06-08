"""PhyloPic (organism-silhouette backend).

PhyloPic (api.phylopic.org) provides free silhouettes of organisms as vector SVG — useful
for cohort / study-design / comparative panels (mouse, rat, human, zebrafish, macaque,
drosophila …), not brain anatomy. Per-image licensing varies (CC0 / CC-BY / CC-BY-SA /
CC-BY-NC), so the license URL on each image is mapped to an id and gated by the registry
(CC0 and CC-BY kept; SA / NC / ND rejected). Names are matched taxonomically (``filter_name``
matches scientific names best), so coverage is best-effort and a miss degrades gracefully.

The v2 API is HATEOAS and build-versioned: the root 307-redirects to ``/?build=<n>`` (our
HttpClient follows it); that build is then required on every query.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

ROOT = "https://api.phylopic.org/"
IMAGES = "https://api.phylopic.org/images"


def _license_from_url(url: str | None) -> str | None:
    """Map a Creative Commons license URL to an id the registry gate understands."""
    u = (url or "").lower()
    if "publicdomain/zero" in u or "/zero/" in u:
        return "cc0-1.0"
    if "publicdomain/mark" in u or "publicdomain" in u:
        return "public-domain"
    if "/by-nc" in u:
        return "cc-by-nc"  # rejected
    if "/by-sa" in u:
        return "cc-by-sa"  # rejected
    if "/by-nd" in u:
        return "cc-by-nd"  # rejected
    if "/licenses/by/" in u:
        return "cc-by-4.0"
    return None


class PhylopicBackend:
    name = "phylopic"

    def __init__(self) -> None:
        self._build: int | None = None

    def _get_build(self, http: HttpClient) -> int:
        if self._build is None:
            self._build = int(http.get_json(ROOT).get("build"))
        return self._build

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        try:
            build = self._get_build(http)
        except Exception:
            return []
        data = http.get_json(
            IMAGES,
            params={
                "build": build,
                "filter_name": term,
                "page": "0",
                "embed_items": "true",
            },
        )
        items = (data.get("_embedded", {}) or {}).get("items", []) or []
        out: list[AssetRecord] = []
        for it in items:
            links = it.get("_links", {}) or {}
            vec = links.get("vectorFile") or {}
            url = vec.get("href")
            if not url:
                continue
            license_id = _license_from_url((links.get("license") or {}).get("href"))
            node = links.get("specificNode") or links.get("generalNode") or {}
            title = node.get("title") or term
            out.append(
                AssetRecord(
                    query=term,
                    title=title,
                    backend=self.name,
                    license=license_id,
                    source_url=url,
                    creators=[it.get("attribution")] if it.get("attribution") else [],
                )
            )
            if len(out) >= size:
                break
        return out
