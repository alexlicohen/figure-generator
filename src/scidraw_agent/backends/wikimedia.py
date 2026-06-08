"""Wikimedia Commons (broad human-neuroanatomy gap-filler backend).

Commons hosts the CC-licensed SVG line drawings SciDraw (rodent/systems) and NIH BIOART
leave thin: human brain anatomy, subcortical structures (thalamus, hippocampus, basal
ganglia), axial/coronal/sagittal slices, and white-matter tracts — including the Servier
SMART donation and the DBCLS Anatomography set. It is **mixed-license**, so the per-file
license is read from the MediaWiki API (``imageinfo`` ``extmetadata``) and gated strictly by
the registry: CC-BY / CC0 / public-domain are kept, CC-BY-SA and non-free are rejected.
SVG-only (``filemime``); Commons' own full-text relevance ranking orders results and the
fetcher takes the first license-compatible one. Attribution (``Artist``) is captured for the
CC-BY credit line. US jurisdiction.

The MediaWiki API mandates a descriptive User-Agent (set in config.USER_AGENT / HttpClient).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str:
    return _TAG_RE.sub("", value or "").strip()


def _norm_license(short: str | None) -> str | None:
    """Map a Commons LicenseShortName to an id the registry gate understands.

    "CC BY 4.0" -> "cc-by-4.0", "CC0" -> "cc0", "Public domain" -> "public-domain",
    "CC BY-SA 4.0" -> "cc-by-sa-4.0" (rejected by the gate).
    """
    if not short:
        return None
    return short.strip().lower().replace(" ", "-")


class WikimediaBackend:
    name = "wikimedia"

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        data = http.get_json(
            COMMONS_API,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{term} filemime:image/svg+xml",
                "gsrnamespace": "6",  # File: namespace
                "gsrlimit": str(max(size, 10)),
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
            },
        )
        pages = (data.get("query", {}) or {}).get("pages", {}) or {}
        out: list[AssetRecord] = []
        # 'index' preserves the search relevance order across the dict of pages.
        for page in sorted(pages.values(), key=lambda p: p.get("index", 1_000_000)):
            ii = (page.get("imageinfo") or [{}])[0]
            url = ii.get("url")
            if not url or not url.lower().endswith(".svg"):
                continue
            title = page.get("title", "").removeprefix("File:")
            em = ii.get("extmetadata", {}) or {}
            license_id = _norm_license((em.get("LicenseShortName", {}) or {}).get("value"))
            artist = _strip_html((em.get("Artist", {}) or {}).get("value"))
            out.append(
                AssetRecord(
                    query=term,
                    title=title,
                    backend=self.name,
                    license=license_id,
                    source_url=url,
                    creators=[artist] if artist else [],
                )
            )
            if len(out) >= size:
                break
        return out
