"""Shared text helpers for backend query/title matching."""

from __future__ import annotations

import re

_STOPWORDS = {"the", "and", "for", "with", "from", "of", "a", "an", "in", "on"}


def tokens(text: str) -> set[str]:
    """Content words (len>=3, minus stopwords), lowercased."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def title_relevant(term: str, title: str) -> bool:
    """True if the title shares a content word with the query (prefix match handles plurals).

    A guard against broad/mixed catalogs returning an off-topic asset for a query.
    """
    q, t = tokens(term), tokens(title)
    if not q:
        return True
    return any(any(tw == qw or tw.startswith(qw) or qw.startswith(tw) for tw in t) for qw in q)
