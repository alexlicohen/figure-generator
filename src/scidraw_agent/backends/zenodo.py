"""SciDraw via the Zenodo REST API (PRIMARY backend).

SciDraw deposits self-identify (their descriptions contain "scidraw.io"), so the search is
scoped with q='"scidraw.io" <term>'. Files download via ``links.self``. A real User-Agent
is mandatory — default agents receive HTTP 403 (set in config.USER_AGENT / HttpClient).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

ZENODO_API = "https://zenodo.org/api/records"


class ZenodoBackend:
    name = "zenodo"

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        data = http.get_json(
            ZENODO_API,
            params={"q": f'"scidraw.io" {term}', "size": size, "sort": "mostviewed"},
        )
        out: list[AssetRecord] = []
        for hit in data.get("hits", {}).get("hits", []):
            md = hit.get("metadata", {})
            svgs = [f for f in hit.get("files", []) if f.get("key", "").endswith(".svg")]
            if not svgs:
                continue
            license_id = (md.get("license") or {}).get("id")
            out.append(
                AssetRecord(
                    query=term,
                    title=md.get("title", "untitled"),
                    backend=self.name,
                    doi=md.get("doi"),
                    license=license_id,
                    source_url=svgs[0].get("links", {}).get("self"),
                    creators=[c.get("name", "") for c in md.get("creators", [])],
                )
            )
        return out
