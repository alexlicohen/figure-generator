"""Structural graphical-abstract generator (no image models).

Lays a GraphicalAbstract (stacked titled sections of cards / tracks / image slots) out as an
editable vector SVG using the house design system. The composition is generated; images are
slotted from real renders (a local PNG/SVG ``path``) or a CC ``asset_query`` — never from an
image model. CC-fetched assets are returned for the manifest's licence/credit trail; local
renders are embedded as-is (the user's own work, no attribution needed). Output still passes
through ``style_guard`` in compose like every other figure.
"""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from ..models import AssetRecord, GAItem, GraphicalAbstract
from ..palette import CATEGORICAL_ORDER, parse_color
from ..theme import StyleSpec
from .anatomical import _embed_asset

if TYPE_CHECKING:
    from ..fetch import AssetFetcher

FONT_FALLBACK = "Arial, Helvetica, sans-serif"
MUTE, HAIR, PANEL = "#5B6B7B", "#C9D2DA", "#F4F6F8"
M = 24.0  # outer margin
MIN_ITEM_W = 200.0  # below this, a row's items reflow to stack vertically
# Column width of the page: figures are rarely full width (most are half / third column).
COLUMN_PX = {"full": 1180.0, "half": 660.0, "third": 440.0}
ICON_PX = 34.0


def _resolve_icon(query: str | None, fetcher) -> str | None:
    """Fetch a clean CC0 Health-Icons line icon for ``query`` (cached); None if unavailable."""
    if not (query and fetcher):
        return None
    try:
        from ..backends.healthicons import HealthIconsBackend

        for rec in HealthIconsBackend().search(query, 3, fetcher.http):
            if fetcher.registry.license_ok(rec.license):
                return fetcher.registry.get_or_download(rec, fetcher.http.get_bytes).local_path
    except Exception:
        return None
    return None


def _embed_icon(path: str, x: float, y: float, size: float, accent: str) -> str:
    """Embed an icon recoloured to ``accent`` (Health-Icons are fill-based monochrome)."""
    try:
        from lxml import etree as _et

        root = _et.fromstring(Path(path).read_bytes())
    except Exception:
        return ""
    for el in root.iter():
        for attr in ("fill", "stroke"):
            v = el.get(attr)
            if v is not None and v != "none":
                el.set(attr, accent)
        tag = el.tag
        local = tag.split("}")[-1] if isinstance(tag, str) else ""
        if local in ("path", "circle", "rect", "polygon", "ellipse") and el.get("fill") is None:
            el.set("fill", accent)
    if not root.get("viewBox"):
        root.set("viewBox", "0 0 48 48")
    root.set("x", f"{x:g}")
    root.set("y", f"{y:g}")
    root.set("width", f"{size:g}")
    root.set("height", f"{size:g}")
    root.set("preserveAspectRatio", "xMidYMid meet")
    from lxml import etree as _et2

    return _et2.tostring(root).decode()


def _white_text(accent: str) -> str:
    rgb = parse_color(accent) or (0, 0, 0)
    return "#000000" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 150 else "#FFFFFF"


class _Canvas:
    def __init__(self, style: StyleSpec) -> None:
        self.f: list[str] = []
        self.font = style.font_family or FONT_FALLBACK
        self.ink = getattr(style, "node_ink", "#222831")

    def text(self, x, y, s, size=12, weight="normal", fill=None, anchor="start"):
        self.f.append(
            f'<text x="{x:g}" y="{y:g}" font-family="{self.font}" font-size="{size:g}" '
            f'font-weight="{weight}" fill="{fill or self.ink}" text-anchor="{anchor}">'
            f"{escape(s)}</text>"
        )

    def rrect(self, x, y, w, h, fill="#FFFFFF", stroke=HAIR, sw=1.4, rx=10):
        self.f.append(
            f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    def header_bar(self, x, y, w, title, accent, hh=26):
        self.f.append(
            f'<path d="M{x + 10:g},{y:g} h{w - 20:g} a10,10 0 0 1 10,10 v{hh - 10:g} h{-w:g} '
            f'v{-(hh - 10):g} a10,10 0 0 1 10,-10 z" fill="{accent}"/>'
        )
        self.text(
            x + w / 2,
            y + hh - 8,
            title,
            size=12.5,
            weight="bold",
            fill=_white_text(accent),
            anchor="middle",
        )

    def raw(self, frag: str):
        if frag:
            self.f.append(frag)


def _accents(ga: GraphicalAbstract, style: StyleSpec) -> None:
    """Assign each item an accent colour (explicit, else cycling the house palette)."""
    colors = list(style.categorical) or list(CATEGORICAL_ORDER)
    i = 0
    for sec in ga.sections:
        for row in sec.as_rows():
            for item in row.items:
                if not item.accent:
                    item.accent = colors[i % len(colors)]
                    i += 1


def _grid_cols(item: GAItem) -> int:
    n = max(1, len(item.images))
    return item.grid_cols or min(n, 4)


def _item_height(item: GAItem) -> float:
    if item.kind == "track":
        return 44 + len(item.steps) * 56 + 6
    if item.kind == "grid":
        rows = math.ceil(max(1, len(item.images)) / _grid_cols(item))
        return (26 if item.title else 8) + rows * 84 + 8
    if item.kind == "image" or item.image:
        return 26 + 104 + (18 if (item.image and item.image.caption) else 6)
    return 26 + (ICON_PX + 8 if item.icon else 0) + max(1, len(item.lines)) * 15 + 18


def _embed_image(img, x, y, w, h, style, fetcher) -> tuple[str, AssetRecord | None, str | None]:
    """(svg_fragment, asset_record_for_credits|None, warning|None). Path > CC > placeholder."""
    if img and img.path and Path(img.path).exists():
        p = img.path
        if p.lower().endswith(".svg"):
            frag = _embed_asset(p, x, y, w, h, style)
            if frag:
                return frag, None, None  # local render — no attribution needed
        else:  # raster render -> self-contained base64 <image>
            mime = "image/jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "image/png"
            b64 = base64.b64encode(Path(p).read_bytes()).decode()
            frag = (
                f'<image x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" '
                f'preserveAspectRatio="xMidYMid meet" href="data:{mime};base64,{b64}"/>'
            )
            return frag, None, None
    if img and img.asset_query and fetcher is not None:
        rec = fetcher.resolve(img.asset_query).record
        if rec and rec.local_path:
            frag = _embed_asset(rec.local_path, x, y, w, h, style)
            if frag:
                return frag, rec, None
    # placeholder
    q = (img.asset_query or img.caption or "render") if img else "render"
    frag = (
        f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="6" fill="#EDF1F4" '
        f'stroke="{HAIR}" stroke-width="1"/>'
        f'<text x="{x + w / 2:g}" y="{y + h / 2:g}" font-size="10" fill="{MUTE}" '
        f'text-anchor="middle">[ slot: {escape(q)} ]</text>'
    )
    rec = AssetRecord(query=q, title=q, backend="none", is_placeholder=True)
    return frag, rec, f"image slot unfilled: {q}"


def _draw_item(c, item, x, y, w, h, style, fetcher):
    assets, warnings = [], []
    accent = item.accent or "#2F5C8A"
    if item.kind == "grid":
        c.rrect(x, y, w, h, stroke=accent, sw=1.6)
        top = y + 26 if item.title else y + 8
        if item.title:
            c.header_bar(x, y, w, item.title, accent)
        n = max(1, len(item.images))
        cols = _grid_cols(item)
        rows = math.ceil(n / cols)
        pad = 8.0
        gw = (w - pad * (cols + 1)) / cols
        gh = (y + h - top - pad * (rows + 1)) / rows
        for i, img in enumerate(item.images):
            r, cc = divmod(i, cols)
            frag, rec, warn = _embed_image(
                img, x + pad + cc * (gw + pad), top + pad + r * (gh + pad), gw, gh, style, fetcher
            )
            c.raw(frag)
            if rec:
                assets.append(rec)
            if warn:
                warnings.append(warn)
        return assets, warnings
    if item.kind == "track":
        c.rrect(x, y, w, h, fill=PANEL, stroke=accent, sw=1.8, rx=12)
        c.header_bar(x, y, w, item.title, accent, hh=32)
        sy = y + 44
        for n, step in enumerate(item.steps, 1):
            c.rrect(x + 12, sy, w - 24, 46, stroke=HAIR, sw=1.2, rx=8)
            c.f.append(f'<circle cx="{x + 30:g}" cy="{sy + 17:g}" r="10" fill="{accent}"/>')
            c.text(
                x + 30,
                sy + 21,
                str(n),
                size=12,
                weight="bold",
                fill=_white_text(accent),
                anchor="middle",
            )
            c.text(x + 48, sy + 18, step.head, size=11, weight="bold")
            if step.detail:
                c.text(x + 48, sy + 34, step.detail, size=9.5, fill=MUTE)
            sy += 56
        return assets, warnings

    # card (optionally with an image) or pure image
    c.rrect(x, y, w, h, stroke=accent, sw=1.6)
    if item.title:
        c.header_bar(x, y, w, item.title, accent)
    cy = y + (26 if item.title else 8)
    if item.image or item.kind == "image":
        frag, rec, warn = _embed_image(item.image, x + 12, cy + 6, w - 24, 96, style, fetcher)
        c.raw(frag)
        if rec:
            assets.append(rec)
        if warn:
            warnings.append(warn)
        cap = item.image.caption if item.image else ""
        if cap:
            c.text(x + w / 2, y + h - 10, cap, size=9.5, fill=MUTE, anchor="middle")
    else:
        text_top = cy + 16
        if item.icon:
            ipath = _resolve_icon(item.icon, fetcher)
            if ipath:
                c.raw(_embed_icon(ipath, x + w / 2 - ICON_PX / 2, cy + 6, ICON_PX, accent))
            else:
                warnings.append(f"icon not found: {item.icon}")
            text_top = cy + ICON_PX + 20
            for i, line in enumerate(item.lines):  # centred under the icon
                c.text(x + w / 2, text_top + i * 14, line, size=10.5, anchor="middle")
        else:
            for i, line in enumerate(item.lines):
                c.text(x + 12, text_top + i * 15, line, size=10.5)
    return assets, warnings


def _connector(c, kind, x, cy):
    if kind == "plus":
        c.text(x, cy + 8, "+", size=28, weight="bold", fill=MUTE, anchor="middle")
    elif kind == "arrow":
        c.f.append(
            f'<line x1="{x - 16:g}" y1="{cy:g}" x2="{x + 8:g}" y2="{cy:g}" stroke="{MUTE}" '
            f'stroke-width="2.4"/><polygon points="{x + 8:g},{cy - 6:g} {x + 8:g},{cy + 6:g} '
            f'{x + 16:g},{cy:g}" fill="{MUTE}"/>'
        )


def _connector_v(c, kind, cx, y):
    if kind == "plus":
        c.text(cx, y + 26, "+", size=24, weight="bold", fill=MUTE, anchor="middle")
    elif kind == "arrow":
        c.f.append(
            f'<line x1="{cx:g}" y1="{y + 6:g}" x2="{cx:g}" y2="{y + 30:g}" stroke="{MUTE}" '
            f'stroke-width="2.4"/><polygon points="{cx - 6:g},{y + 30:g} {cx + 6:g},{y + 30:g} '
            f'{cx:g},{y + 38:g}" fill="{MUTE}"/>'
        )


def _draw_row_vertical(c, row, y, W, style, fetcher) -> tuple[float, list, list]:
    """Narrow column: stack the row's items full-width with vertical connectors between them."""
    iw = W - 2 * M
    vgap = {"arrow": 42.0, "plus": 36.0}.get(row.connector, 16.0)
    cy, assets, warnings = y, [], []
    for idx, item in enumerate(row.items):
        ih = _item_height(item)
        a, w_ = _draw_item(c, item, M, cy, iw, ih, style, fetcher)
        assets += a
        warnings += w_
        cy += ih
        if idx < len(row.items) - 1:
            _connector_v(c, row.connector, M + iw / 2, cy)
            cy += vgap
    return cy - y, assets, warnings


def _draw_row(c, row, y, W, style, fetcher) -> tuple[float, list, list]:
    """Lay a single row of items left-to-right; reflow to vertical when too narrow."""
    items = row.items
    if not items:
        return 0.0, [], []
    gap = {"arrow": 50.0, "plus": 40.0}.get(row.connector, 26.0)
    avail = (W - 2 * M) - gap * max(0, len(items) - 1)
    wsum = sum(it.weight for it in items) or 1.0
    smallest = min(avail * (it.weight / wsum) for it in items)
    if len(items) > 1 and smallest < MIN_ITEM_W:
        return _draw_row_vertical(c, row, y, W, style, fetcher)
    row_h = max(_item_height(it) for it in items)
    assets, warnings = [], []
    x = M
    for idx, item in enumerate(items):
        iw = avail * (item.weight / wsum)
        a, w_ = _draw_item(c, item, x, y, iw, row_h, style, fetcher)
        assets += a
        warnings += w_
        x += iw
        if idx < len(items) - 1:
            _connector(c, row.connector, x + gap / 2, y + row_h / 2)
            x += gap
    return row_h, assets, warnings


def build_graphical_abstract_svg(
    ga: GraphicalAbstract, style: StyleSpec, fetcher: AssetFetcher | None = None
) -> tuple[str, list[AssetRecord], list[str]]:
    _accents(ga, style)
    c = _Canvas(style)
    W = ga.width if ga.width and ga.width > 0 else COLUMN_PX.get(ga.column, COLUMN_PX["half"])
    assets: list[AssetRecord] = []
    warnings: list[str] = []

    y = M
    if ga.title:
        # scale the title down so a long title still fits a narrow column
        tsize = max(11.0, min(16.0, (W - 2 * M) / (0.52 * max(1, len(ga.title)))))
        c.text(W / 2, y + 6, ga.title, size=tsize, weight="bold", anchor="middle")
        y += tsize + 14

    for sec in ga.sections:
        c.f.append(f'<rect x="{M:g}" y="{y - 12:g}" width="6" height="18" rx="2" fill="{c.ink}"/>')
        c.text(M + 14, y + 2, sec.title, size=14, weight="bold")
        y += 16

        rows = sec.as_rows()
        for ri, row in enumerate(rows):
            row_h, a, w_ = _draw_row(c, row, y, W, style, fetcher)
            assets += a
            warnings += w_
            y += row_h + (14 if ri < len(rows) - 1 else 0)
        y += 30

    H = y
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:g}" height="{H:g}" '
        f'viewBox="0 0 {W:g} {H:g}"><rect width="{W:g}" height="{H:g}" fill="white"/>'
        + "".join(c.f)
        + "</svg>"
    )
    return svg, assets, warnings
