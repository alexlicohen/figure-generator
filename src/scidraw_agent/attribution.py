"""Paste-ready asset credit lines for the figure legend.

Reused image assets belong in a **figure-legend credit line** (or a "Figure credits" note),
NOT the bibliography — references are for literature you cite. CC-BY assets *require*
attribution (Title / Author / Source / License); CC0 and public-domain do not, but the
source is credited as a courtesy. SciDraw/Zenodo assets also carry a DOI and may be cited
formally if a journal prefers. This module turns the AssetRecords behind a figure into:
- one short credit sentence per asset, and
- a single combined line ready to paste into the legend,
both also recorded in the manifest and written to ``figure.credits.txt``.
"""

from __future__ import annotations

from .models import AssetRecord, Credits

# license id -> (display name, canonical URL)
_LICENSES: dict[str, tuple[str, str]] = {
    "cc0-1.0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "cc0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "public-domain": ("public domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
}

_SOURCES: dict[str, str] = {
    "zenodo": "SciDraw (via Zenodo)",
    "bioart": "NIH BIOART Source",
    "bioicons": "Bioicons",
    "wikimedia": "Wikimedia Commons",
    "healthicons": "Health Icons",
    "phylopic": "PhyloPic",
}

# Licenses that do not legally require attribution (still credited as a courtesy).
_NO_ATTRIB_REQUIRED = {"cc0-1.0", "cc0", "public-domain"}


def license_label(license_id: str | None) -> tuple[str, str]:
    """(display name, url) for a normalized license id; handles any CC-BY version."""
    if not license_id:
        return ("license unknown", "")
    lic = license_id.strip().lower()
    if lic in _LICENSES:
        return _LICENSES[lic]
    if "public" in lic or "zero" in lic:
        return ("public domain", "https://creativecommons.org/publicdomain/mark/1.0/")
    if lic.startswith("cc-by"):
        version = lic.removeprefix("cc-by-").upper() if lic != "cc-by" else "4.0"
        name = "CC BY" + ("-SA" if "-sa" in lic else "") + f" {version}".rstrip()
        return (name, f"https://creativecommons.org/licenses/by/{version if version else '4.0'}/")
    return (license_id, "")  # permissive/code license id verbatim


def _source(record: AssetRecord) -> str:
    return _SOURCES.get(record.backend, record.backend.replace("_", " ").title())


def _authors(record: AssetRecord) -> str:
    # collapse internal whitespace/newlines (Wikimedia Artist HTML can be multi-line)
    return ", ".join(" ".join(c.split()) for c in record.creators if c and c.strip())


def _is_public(license_id: str | None) -> bool:
    return (license_id or "").strip().lower() in _NO_ATTRIB_REQUIRED


def _initials(name: str) -> str:
    """'Last, First Middle' -> 'F. Last'; pass other forms through cleaned up."""
    name = " ".join(name.split())
    if "," in name:
        last, first = (p.strip() for p in name.split(",", 1))
        return f"{first[:1]}. {last}".strip() if first else last
    return name


def asset_credit(record: AssetRecord) -> str | None:
    """A full per-asset credit sentence, or None for a placeholder (no real asset)."""
    if record.is_placeholder:
        return None
    name, _ = license_label(record.license)
    by = f" by {_authors(record)}" if _authors(record) else ""
    locus = f" (doi:{record.doi})" if record.doi else ""
    return f'"{record.title}"{by} — {_source(record)}{locus}, {name}.'


def figure_credit_line(records: list[AssetRecord]) -> str:
    """One combined sentence for the legend, deduplicated by (title, source)."""
    parts: list[str] = []
    seen: set[tuple[str, str]] = set()
    for r in records:
        if r.is_placeholder:
            continue
        key = (r.title, r.backend)
        if key in seen:
            continue
        seen.add(key)
        name, _ = license_label(r.license)
        by = f"{_authors(r)}, " if _authors(r) else ""
        parts.append(f'"{r.title}" ({by}{_source(r)}, {name})')
    if not parts:
        return ""
    return "Illustrative assets adapted from open repositories: " + "; ".join(parts) + "."


def figure_credit_line_compact(records: list[AssetRecord]) -> str:
    """The practical figure convention: grouped by Source+License, titles dropped, authors as
    initials (CC-BY only). CC requires attribution "reasonable to the medium" — this keeps the
    creator + source + license CC-BY needs while dropping the droppable Title.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    order: list[tuple[str, str]] = []
    for r in records:
        if r.is_placeholder:
            continue
        name, _ = license_label(r.license)
        src = _source(r).split(" (")[0]  # drop "(via Zenodo)"-style detail for compactness
        key = (src, name)
        if key not in groups:
            groups[key] = []
            order.append(key)
        if not _is_public(r.license):  # public-domain/CC0 need no author credit
            for c in r.creators:
                ini = _initials(c) if c and c.strip() else ""
                if ini and ini not in groups[key]:
                    groups[key].append(ini)
    if not order:
        return ""
    parts = [
        f"{src} ({', '.join(authors)}; {name})"
        if (authors := groups[(src, name)])
        else f"{src} ({name})"
        for (src, name) in order
    ]
    return "Adapted from " + "; ".join(parts) + "."


def build_credits(records: list[AssetRecord]) -> Credits:
    per = [c for r in records if (c := asset_credit(r))]
    required = any(
        (not r.is_placeholder) and (r.license or "").strip().lower() not in _NO_ATTRIB_REQUIRED
        for r in records
    )
    return Credits(
        legend_line=figure_credit_line_compact(records),  # default = the compact convention
        legend_line_full=figure_credit_line(records),
        per_asset=per,
        attribution_required=required,
    )


def credits_text(credits: Credits) -> str:
    """The contents of figure.credits.txt."""
    if not credits.per_asset:
        return "No imported assets — nothing to attribute.\n"
    lines = [
        "IMAGE CREDITS — paste the legend line below into your figure legend.",
        "",
        "These are figure-legend credit lines, not bibliography references.",
        (
            "At least one asset is CC-BY and MUST be credited."
            if credits.attribution_required
            else "All assets are CC0 / public domain (credit not required, included as courtesy)."
        ),
        "",
        "── Legend credit line (compact — recommended for figures) ──",
        credits.legend_line,
        "",
        "── Full credit (Title / Author / Source / License) ──",
        credits.legend_line_full,
        "",
        "── Per asset ──",
    ]
    lines += [f"- {c}" for c in credits.per_asset]
    lines += [
        "",
        "Note: SciDraw/Zenodo assets carry a DOI and may also be cited formally if your "
        "journal prefers. Full machine-readable provenance is in figure.manifest.json.",
        "",
    ]
    return "\n".join(lines)
