"""Anatomical schematic generator.

Lays entities into a grid, embeds CC-licensed organic assets when the fetcher finds one,
and otherwise draws a labelled placeholder (degrade gracefully — A4). Related entities
(same `group`) sit on a subtle common-region tint (Gestalt grouping, not bounding boxes).
Stylized output is tagged "schematic — not to scale" to avoid implying false precision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from lxml import etree

from ..models import FigureSchema, FigureType
from ..palette import PaletteRegistry, parse_color
from ..theme import StyleSpec
from . import GeneratorResult

if TYPE_CHECKING:
    from ..fetch import AssetFetcher

SLOT_W, SLOT_H, PAD, LABEL_H = 200.0, 150.0, 28.0, 26.0
PLACEHOLDER_FILL = "#EEEEEE"
PLACEHOLDER_STROKE = "#999999"
SVG_NS = "http://www.w3.org/2000/svg"

REAL_RENDER_HINT = (
    "no asset found; using a labelled placeholder. For a real data render use "
    "nilearn / Surf Ice / MRIcroGL / FSLeyes."
)


def _tint(hex_color: str) -> str:
    rgb = parse_color(hex_color) or (153, 153, 153)
    light = tuple(round(c + (255 - c) * 0.85) for c in rgb)
    return "#{:02X}{:02X}{:02X}".format(*light)


def _darken_pale_achromatic(rgb: tuple[int, int, int]) -> tuple[int, int, int] | None:
    """Darken a light, near-grey colour so it reads on white; leave colours/darks alone.

    Some CC assets are drawn entirely in pale grey (e.g. SciDraw's pyramidal neuron) and
    vanish on a white page. We darken only colours that are both LIGHT and ACHROMATIC (low
    channel spread) — light *coloured* fills (e.g. a diagram's pale-teal regions) are kept.
    """
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    spread = max(rgb) - min(rgb)
    if 165 <= lum <= 244 and spread < 30:
        return tuple(round(c * 0.6) for c in rgb)
    return None


def _boost_contrast(root: etree._Element) -> None:
    """Rewrite pale-grey fills/strokes (attr or inline style) to a readable tone."""
    for el in root.iter():
        for attr in ("fill", "stroke"):
            val = el.get(attr)
            rgb = parse_color(val) if val else None
            if rgb and (dark := _darken_pale_achromatic(rgb)):
                el.set(attr, "#{:02X}{:02X}{:02X}".format(*dark))
        style = el.get("style")
        if style and (":" in style):
            props = dict(
                (k.strip(), v.strip())
                for chunk in style.split(";")
                if ":" in chunk
                for k, v in [chunk.split(":", 1)]
            )
            changed = False
            for prop in ("fill", "stroke"):
                rgb = parse_color(props[prop]) if props.get(prop) else None
                if rgb and (dark := _darken_pale_achromatic(rgb)):
                    props[prop] = "#{:02X}{:02X}{:02X}".format(*dark)
                    changed = True
            if changed:
                el.set("style", ";".join(f"{k}:{v}" for k, v in props.items()))


def _embed_asset(path: str, x: float, y: float, w: float, h: float) -> str | None:
    try:
        root = etree.fromstring(open(path, "rb").read())
    except (OSError, etree.XMLSyntaxError):
        return None
    _boost_contrast(root)
    if not root.get("viewBox"):
        ow, oh = root.get("width", "100"), root.get("height", "100")
        import re

        ow = re.sub(r"[^0-9.]", "", ow) or "100"
        oh = re.sub(r"[^0-9.]", "", oh) or "100"
        root.set("viewBox", f"0 0 {ow} {oh}")
    root.set("x", f"{x:g}")
    root.set("y", f"{y:g}")
    root.set("width", f"{w:g}")
    root.set("height", f"{h:g}")
    root.set("preserveAspectRatio", "xMidYMid meet")
    return etree.tostring(root).decode()


class AnatomicalGenerator:
    figure_types = {FigureType.ANATOMICAL}

    def generate(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
        *,
        fetcher: AssetFetcher | None = None,
    ) -> GeneratorResult:
        entities = schema.entities
        cols = max(1, min(3, len(entities)))
        rows = (len(entities) + cols - 1) // cols
        width = PAD + cols * (SLOT_W + PAD)
        height = PAD + rows * (SLOT_H + LABEL_H + PAD) + 24

        pos: dict[str, tuple[float, float]] = {}
        for i, e in enumerate(entities):
            r, c = divmod(i, cols)
            x = PAD + c * (SLOT_W + PAD)
            y = PAD + r * (SLOT_H + LABEL_H + PAD)
            pos[e.id] = (x, y)

        body: list[str] = []
        body.extend(self._group_regions(entities, pos, palette))

        assets, warnings = [], []
        for e in entities:
            x, y = pos[e.id]
            record = None
            if fetcher is not None:
                query = e.suggested_asset_query or e.label
                record = fetcher.resolve(query).record
            if record and record.local_path:
                embedded = _embed_asset(record.local_path, x, y, SLOT_W, SLOT_H)
                if embedded:
                    body.append(embedded)
                    assets.append(record)
                else:
                    record = None
            if not record:
                body.append(self._placeholder(x, y, e.label))
                from ..models import AssetRecord

                q = e.suggested_asset_query or e.label
                assets.append(
                    AssetRecord(query=q, title=e.label, backend="none", is_placeholder=True)
                )
                warnings.append(f"'{q}': {REAL_RENDER_HINT}")
            body.append(self._caption(x, y, e.label, style))

        body.append(
            f'<text x="{PAD}" y="{height - 8:g}" font-size="11" '
            f'font-family="{style.font_family}" fill="#666666">schematic — not to scale</text>'
        )
        svg = (
            f'<svg xmlns="{SVG_NS}" width="{width:g}" height="{height:g}" '
            f'viewBox="0 0 {width:g} {height:g}">' + "".join(body) + "</svg>"
        )
        return GeneratorResult(svg=svg, assets=assets, warnings=warnings)

    def _group_regions(self, entities, pos, palette) -> list[str]:
        regions: list[str] = []
        groups: dict[str, list[str]] = {}
        for e in entities:
            if e.group:
                groups.setdefault(e.group, []).append(e.id)
        for group, ids in groups.items():
            if len(ids) < 2:
                continue
            xs = [pos[i][0] for i in ids]
            ys = [pos[i][1] for i in ids]
            x0, y0 = min(xs) - 12, min(ys) - 12
            x1 = max(xs) + SLOT_W + 12
            y1 = max(ys) + SLOT_H + LABEL_H + 12
            color = palette.assign(group).color
            regions.append(
                f'<rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" '
                f'rx="12" fill="{_tint(color)}" stroke="none"/>'
            )
        return regions

    def _placeholder(self, x, y, label) -> str:
        return (
            f'<rect x="{x:g}" y="{y:g}" width="{SLOT_W:g}" height="{SLOT_H:g}" rx="8" '
            f'fill="{PLACEHOLDER_FILL}" stroke="{PLACEHOLDER_STROKE}" stroke-width="1" '
            f'stroke-dasharray="6,4"/>'
            f'<text x="{x + SLOT_W / 2:g}" y="{y + SLOT_H / 2:g}" font-size="12" '
            f'text-anchor="middle" fill="#888888">{escape(label)}</text>'
        )

    def _caption(self, x, y, label, style) -> str:
        return (
            f'<text x="{x + SLOT_W / 2:g}" y="{y + SLOT_H + 18:g}" font-size="12" '
            f'text-anchor="middle" font-family="{style.font_family}" fill="#000000">'
            f"{escape(label)}</text>"
        )
