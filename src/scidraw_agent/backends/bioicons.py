"""bioicons (FALLBACK backend) — CC0/CC-BY/permissive SVG icons.

Index: a single ``icons.json`` listing {name, category, license, author}. The SVG path is
``static/icons/<license>/<category>/<author>/<name>.svg``. The index is fetched once and
cached in memory for the fetcher's lifetime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

_RAW = "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons"
INDEX_URL = f"{_RAW}/icons.json"

# bioicons uses short license tokens; normalise to ids the license gate understands.
_LICENSE_MAP = {"cc-0": "cc0-1.0", "cc0": "cc0-1.0", "cc-by": "cc-by-4.0"}


class BioiconsBackend:
    name = "bioicons"

    def __init__(self) -> None:
        self._index: list[dict] | None = None

    def _load_index(self, http: HttpClient) -> list[dict]:
        if self._index is None:
            self._index = http.get_json(INDEX_URL)  # type: ignore[assignment]
        return self._index or []

    @staticmethod
    def _norm_license(token: str) -> str:
        return _LICENSE_MAP.get(token.strip().lower(), token.strip().lower())

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        needle = term.lower().replace("_", " ")
        out: list[AssetRecord] = []
        for entry in self._load_index(http):
            haystack = f"{entry.get('name', '')} {entry.get('category', '')}".lower().replace(
                "_", " "
            )
            if needle not in haystack:
                continue
            rel = f"{entry['license']}/{entry['category']}/{entry['author']}/{entry['name']}.svg"
            url = f"{_RAW}/{rel}"
            out.append(
                AssetRecord(
                    query=term,
                    title=entry["name"].replace("_", " "),
                    backend=self.name,
                    license=self._norm_license(entry["license"]),
                    source_url=url,
                    creators=[entry.get("author", "")],
                )
            )
            if len(out) >= size:
                break
        return out
