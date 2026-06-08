"""SciDraw via the Zenodo REST API (PRIMARY backend).

SciDraw deposits self-identify (their descriptions contain "scidraw.io"), so the search
requires that phrase (``q='+"scidraw.io" <term>'``) and ranks by relevance
(``sort=bestmatch``) — NOT ``mostviewed``, which lets a hugely-viewed unrelated deposit
outrank the actual match. Because Zenodo still returns *something* for a term SciDraw lacks
(e.g. "thalamus" -> "Hepatocyte"), a title-relevance gate drops hits whose title shares no
content word with the query, so a miss returns nothing (graceful fallback) instead of a
false match. Files download via ``links.self``. A real User-Agent is mandatory — default
agents receive HTTP 403 (set in config.USER_AGENT / HttpClient).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

ZENODO_API = "https://zenodo.org/api/records"

# Words that carry no discriminating meaning, so they must not make a title "relevant".
_STOPWORDS = {"the", "and", "for", "with", "from", "scidraw"}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _title_relevant(term: str, title: str) -> bool:
    """True if the title shares a content word with the query (prefix match handles plurals).

    Guards against Zenodo returning a generic SciDraw deposit for a term SciDraw lacks.
    """
    q, t = _tokens(term), _tokens(title)
    if not q:
        return True  # nothing to discriminate on -> don't over-filter
    return any(any(tw == qw or tw.startswith(qw) or qw.startswith(tw) for tw in t) for qw in q)


class ZenodoBackend:
    name = "zenodo"

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        data = http.get_json(
            ZENODO_API,
            params={"q": f'+"scidraw.io" {term}', "size": size, "sort": "bestmatch"},
        )
        out: list[AssetRecord] = []
        for hit in data.get("hits", {}).get("hits", []):
            md = hit.get("metadata", {})
            svgs = [f for f in hit.get("files", []) if f.get("key", "").endswith(".svg")]
            if not svgs:
                continue
            title = md.get("title", "untitled")
            if not _title_relevant(term, title):
                continue  # drop off-topic deposits (false-match guard)
            license_id = (md.get("license") or {}).get("id")
            out.append(
                AssetRecord(
                    query=term,
                    title=title,
                    backend=self.name,
                    doi=md.get("doi"),
                    license=license_id,
                    source_url=svgs[0].get("links", {}).get("self"),
                    creators=[c.get("name", "") for c in md.get("creators", [])],
                )
            )
        return out
