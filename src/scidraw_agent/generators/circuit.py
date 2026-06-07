"""Mechanistic circuit generator (templated SVG via drawsvg).

Edge *type* is encoded by arrowhead shape, never by colour alone:
- excitatory / projection / flow -> solid line, filled pointed arrowhead
- inhibitory                      -> solid line, flat T-bar head
- modulatory                     -> dashed line, open arrowhead
A compact legend resolves the encoding. Node fill comes from the shared PaletteRegistry.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import drawsvg as draw

from ..models import (
    EXCITATORY_RELATIONS,
    INHIBITORY_RELATIONS,
    MODULATORY_RELATIONS,
    EdgeRelation,
    FigureSchema,
    FigureType,
)
from ..palette import PaletteRegistry, parse_color
from ..theme import StyleSpec
from . import GeneratorResult

if TYPE_CHECKING:
    from ..fetch import AssetFetcher

EDGE_COLOR = "#333333"
EDGE_W = 1.4
NODE_H = 46.0
NODE_STROKE = "#333333"
FONT = 13.0


def _node_width(label: str) -> float:
    return max(70.0, min(190.0, 30.0 + 7.2 * len(label)))


def _text_color(fill: str) -> str:
    rgb = parse_color(fill) or (0, 0, 0)
    luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return "#000000" if luminance > 140 else "#FFFFFF"


def _boundary(cx, cy, hw, hh, dx, dy):
    """Intersection of the ray (dx,dy) from box centre with the box edge."""
    if dx == 0 and dy == 0:
        return cx, cy
    tx = hw / abs(dx) if dx else math.inf
    ty = hh / abs(dy) if dy else math.inf
    t = min(tx, ty)
    return cx + dx * t, cy + dy * t


class CircuitGenerator:
    figure_types = {FigureType.MECHANISTIC_CIRCUIT}

    def generate(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
        *,
        fetcher: AssetFetcher | None = None,
    ) -> GeneratorResult:
        entities = schema.entities
        margin, gap = 50.0, 80.0
        widths = {e.id: _node_width(e.label) for e in entities}
        x = margin
        cy = 90.0
        centers: dict[str, tuple[float, float, float]] = {}
        for e in entities:
            w = widths[e.id]
            centers[e.id] = (x + w / 2, cy, w)
            x += w + gap
        total_w = max(360.0, x - gap + margin)
        total_h = cy + NODE_H / 2 + 110.0

        d = draw.Drawing(total_w, total_h, origin=(0, 0))

        # Edges first (under nodes).
        relations_present: set[EdgeRelation] = set()
        for edge in schema.edges:
            if edge.source not in centers or edge.target not in centers:
                continue
            relations_present.add(edge.relation)
            self._draw_edge(d, centers, widths, edge)

        # Nodes.
        for e in entities:
            cx, cyy, w = centers[e.id]
            fill = palette.assign(e.group or e.id).color
            d.append(
                draw.Rectangle(
                    cx - w / 2,
                    cyy - NODE_H / 2,
                    w,
                    NODE_H,
                    rx=8,
                    fill=fill,
                    stroke=NODE_STROKE,
                    stroke_width=1.2,
                )
            )
            d.append(
                draw.Text(
                    e.label,
                    FONT,
                    cx,
                    cyy,
                    center=True,
                    fill=_text_color(fill),
                    font_family=style.font_family,
                )
            )

        self._legend(d, relations_present, margin, total_h - 70.0, style)
        return GeneratorResult(svg=d.as_svg(), warnings=_dangling_warnings(schema))

    # -- drawing helpers --------------------------------------------------- #
    def _draw_edge(self, d, centers, widths, edge) -> None:
        sx, sy, sw = centers[edge.source]
        tx, ty, tw = centers[edge.target]
        dx, dy = tx - sx, ty - sy
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        x1, y1 = _boundary(sx, sy, sw / 2, NODE_H / 2, ux, uy)
        x2, y2 = _boundary(tx, ty, tw / 2, NODE_H / 2, -ux, -uy)

        rel = edge.relation
        dashed = rel in MODULATORY_RELATIONS
        # stop the line short of the head so the head sits at the boundary
        head_back = 10.0
        lx2, ly2 = x2 - ux * head_back, y2 - uy * head_back
        line = draw.Line(
            x1,
            y1,
            lx2,
            ly2,
            stroke=EDGE_COLOR,
            stroke_width=EDGE_W,
            stroke_dasharray="5,4" if dashed else None,
        )
        d.append(line)

        if rel in INHIBITORY_RELATIONS:
            self._tbar(d, x2, y2, ux, uy)
        elif rel in MODULATORY_RELATIONS:
            self._arrow(d, x2, y2, ux, uy, filled=False)
        else:  # excitatory / projection / flow / other
            self._arrow(d, x2, y2, ux, uy, filled=True)

        if edge.label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 6
            d.append(draw.Text(edge.label, 11, mx, my, center=True, fill=EDGE_COLOR))

    def _arrow(self, d, x, y, ux, uy, *, filled: bool) -> None:
        size = 11.0
        px, py = -uy, ux  # perpendicular
        bx, by = x - ux * size, y - uy * size
        p1 = (bx + px * size * 0.5, by + py * size * 0.5)
        p2 = (bx - px * size * 0.5, by - py * size * 0.5)
        d.append(
            draw.Lines(
                x,
                y,
                p1[0],
                p1[1],
                p2[0],
                p2[1],
                close=True,
                fill=EDGE_COLOR if filled else "#FFFFFF",
                stroke=EDGE_COLOR,
                stroke_width=EDGE_W,
            )
        )

    def _tbar(self, d, x, y, ux, uy) -> None:
        px, py = -uy, ux
        half = 9.0
        d.append(
            draw.Line(
                x + px * half,
                y + py * half,
                x - px * half,
                y - py * half,
                stroke=EDGE_COLOR,
                stroke_width=2.0,
            )
        )

    def _legend(self, d, relations, x, y, style) -> None:
        items = []
        if (
            relations & EXCITATORY_RELATIONS
            or EdgeRelation.OTHER in relations
            or EdgeRelation.PREDICTS in relations
        ):
            items.append(("excitatory / projection", "arrow"))
        if relations & INHIBITORY_RELATIONS:
            items.append(("inhibitory", "tbar"))
        if relations & MODULATORY_RELATIONS:
            items.append(("modulatory", "dashed"))
        for i, (label, kind) in enumerate(items):
            ly = y + i * 18
            d.append(
                draw.Line(
                    x,
                    ly,
                    x + 28,
                    ly,
                    stroke=EDGE_COLOR,
                    stroke_width=EDGE_W,
                    stroke_dasharray="5,4" if kind == "dashed" else None,
                )
            )
            if kind == "tbar":
                d.append(
                    draw.Line(x + 28, ly - 7, x + 28, ly + 7, stroke=EDGE_COLOR, stroke_width=2)
                )
            else:
                self._arrow(d, x + 30, ly, 1, 0, filled=(kind != "dashed"))
            d.append(
                draw.Text(label, 11, x + 40, ly + 4, fill="#000000", font_family=style.font_family)
            )


def _dangling_warnings(schema: FigureSchema) -> list[str]:
    return [
        f"Edge references unknown entity: {e.source}->{e.target}" for e in schema.dangling_edges()
    ]
