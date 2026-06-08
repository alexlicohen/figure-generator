"""Health Icons (CC0 medical/anatomy line-icon fallback).

Health Icons (resolvetosavelives/healthicons) is a public-domain (CC0) set of clean medical
line icons — including a handful relevant here (Brain, Nerve, Head, Skull, Skeleton, and
Head Circumference, which is squarely pediatric-neuro). A single ``meta-data.json`` indexes
every icon ``{id, category, path, tags, title}``; the SVG is at a predictable raw path. The
index is fetched once and cached for the fetcher's lifetime. CC0 -> always passes the gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import AssetRecord
from ._text import tokens

if TYPE_CHECKING:
    from ..fetch import HttpClient

_RAW = "https://raw.githubusercontent.com/resolvetosavelives/healthicons/main/public/icons"
INDEX_URL = f"{_RAW}/meta-data.json"
# Outline = line-drawing style, which matches the schematic aesthetic; filled also exists.
SVG_URL = _RAW + "/svg/outline/{path}.svg"
LICENSE = "cc0-1.0"


class HealthIconsBackend:
    name = "healthicons"

    def __init__(self) -> None:
        self._index: list[dict] | None = None

    def _load_index(self, http: HttpClient) -> list[dict]:
        if self._index is None:
            self._index = http.get_json(INDEX_URL)  # type: ignore[assignment]
        return self._index or []

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        needle = tokens(term)
        if not needle:
            return []

        def _hit(words: set[str]) -> bool:
            return all(any(w == n or w.startswith(n) for w in words) for n in needle)

        title_hits: list[AssetRecord] = []
        tag_hits: list[AssetRecord] = []
        for entry in self._load_index(http):
            title = entry.get("title", entry.get("id", "icon"))
            in_title = _hit(tokens(title))
            in_all = in_title or _hit(
                tokens(f"{entry.get('path', '')} " + " ".join(entry.get("tags", [])))
            )
            if not in_all:
                continue
            rec = AssetRecord(
                query=term,
                title=title,
                backend=self.name,
                license=LICENSE,
                source_url=SVG_URL.format(path=entry["path"]),
                creators=["Health Icons (Resolve to Save Lives)"],
            )
            (title_hits if in_title else tag_hits).append(rec)
        # exact title matches first, then tag/path matches (a "Skull" body part beats a
        # "Death" icon merely tagged "skull").
        return (title_hits + tag_hits)[:size]
