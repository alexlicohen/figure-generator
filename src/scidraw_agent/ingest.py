"""Ingest paper Methods / grant Specific Aims from PDF / text / pasted strings.

PyMuPDF extracts PDF text; regex locates the relevant section by heading. When the heading
is absent (common in grants with idiosyncratic formatting), the whole text is returned and
the extractor (Claude) does the section-finding — the mandatory fallback path.
"""

from __future__ import annotations

import re
from pathlib import Path

_METHODS_START = re.compile(
    r"(?im)^\s*(?:\d+\.?\s*)?(materials\s+and\s+methods|methods|experimental\s+procedures)\b"
)
_AIMS_START = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(specific\s+aims|aims)\b")
_METHODS_STOP = re.compile(r"(?im)^\s*(?:\d+\.?\s*)?(results|discussion|conclusion|references)\b")
_AIMS_STOP = re.compile(
    r"(?im)^\s*(?:\d+\.?\s*)?(research\s+strategy|background|significance|approach|references)\b"
)


def read_file(path: str | Path) -> str:
    """Read text from a .pdf (PyMuPDF), or a .txt/.md/other plain-text file."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return _read_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    try:
        import pymupdf as fitz
    except ModuleNotFoundError:  # pragma: no cover - older wheel name
        import fitz
    parts = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return "\n".join(parts)


def _section(text: str, start: re.Pattern, stop: re.Pattern) -> str | None:
    m = start.search(text)
    if not m:
        return None
    body_start = m.end()
    stop_m = stop.search(text, body_start)
    body_end = stop_m.start() if stop_m else len(text)
    return text[body_start:body_end].strip() or None


def extract_methods(text: str) -> str | None:
    return _section(text, _METHODS_START, _METHODS_STOP)


def extract_aims(text: str) -> str | None:
    return _section(text, _AIMS_START, _AIMS_STOP)


def ingest(source: str | Path, *, section: str | None = None) -> str:
    """Return the text to extract from.

    ``source`` may be a file path or a raw pasted string. ``section`` ('methods' | 'aims')
    narrows to that section when its heading is found; otherwise the full text is returned
    (Claude then finds the relevant content).
    """
    if isinstance(source, Path) or (isinstance(source, str) and _looks_like_path(source)):
        text = read_file(source)
    else:
        text = str(source)

    if section == "methods":
        return extract_methods(text) or text
    if section == "aims":
        return extract_aims(text) or text
    return text


def _looks_like_path(s: str) -> bool:
    if len(s) > 400 or "\n" in s:
        return False
    return Path(s).exists()
