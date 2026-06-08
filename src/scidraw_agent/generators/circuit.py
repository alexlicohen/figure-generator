"""Mechanistic circuit generator (Graphviz layout + edge-type arrowheads).

Edge *type* is encoded by arrowhead shape, never by colour alone:
- excitatory / projection / flow -> solid line, filled arrowhead   (Graphviz ``normal``)
- inhibitory                      -> solid line, flat T-bar head     (Graphviz ``tee``)
- modulatory                     -> dashed line, open arrowhead      (Graphviz ``empty``)

Graphviz does the layout so edges never run *through* nodes — the previous hand-rolled
single-row drawer placed non-adjacent edges (e.g. M1->spinal cord with an interneuron
between them) straight through the intervening node, misrepresenting the circuit. A compact
legend is appended as SVG (only for the relation types present); node fill comes from the
shared PaletteRegistry. The whole SVG still passes through ``style_guard`` in compose.
Requires the system ``dot`` binary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import graphviz
from lxml import etree

from ..models import (
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
SVG_NS = "http://www.w3.org/2000/svg"


def _font_color(fill: str) -> str:
    rgb = parse_color(fill) or (0, 0, 0)
    return "black" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 140 else "white"


def _edge_attrs(rel: EdgeRelation) -> dict[str, str]:
    if rel in INHIBITORY_RELATIONS:
        return {"arrowhead": "tee", "style": "solid"}
    if rel in MODULATORY_RELATIONS:
        return {"arrowhead": "empty", "style": "dashed"}
    return {"arrowhead": "normal", "style": "solid"}  # excitatory / projection / flow / other


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
        outline = getattr(style, "node_style", "filled") == "outline"
        ink = getattr(style, "node_ink", EDGE_COLOR)
        g = graphviz.Digraph("circuit")
        g.attr(rankdir="LR", bgcolor="white", nodesep="0.4", ranksep="0.7")
        g.attr(
            "node",
            shape="box",
            style="filled,rounded",
            fontname="Arial",
            fontsize="12",
            penwidth="1.8" if outline else "1.2",
            color=ink,
            margin="0.18,0.12",
        )
        g.attr(
            "edge",
            color=EDGE_COLOR,
            penwidth="1.4",
            arrowsize="0.9",
            fontname="Arial",
            fontsize="11",
        )

        for e in schema.entities:
            accent = palette.assign(e.group or e.id).color
            if outline:
                g.node(e.id, e.label, fillcolor="white", color=accent, fontcolor=ink)
            else:
                g.node(e.id, e.label, fillcolor=accent, fontcolor=_font_color(accent))

        ids = schema.entity_ids()
        relations: set[EdgeRelation] = set()
        for edge in schema.edges:
            if edge.source in ids and edge.target in ids:
                relations.add(edge.relation)
                g.edge(
                    edge.source, edge.target, label=edge.label or "", **_edge_attrs(edge.relation)
                )

        svg = g.pipe(format="svg").decode("utf-8")
        svg = _append_legend(svg, relations, style)
        return GeneratorResult(svg=svg, warnings=_dangling_warnings(schema))


# --------------------------------------------------------------------------- #
# Legend (appended below the Graphviz drawing, in root viewBox coordinates)
# --------------------------------------------------------------------------- #
def _legend_items(relations: set[EdgeRelation]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    excitatory = relations - INHIBITORY_RELATIONS - MODULATORY_RELATIONS
    if excitatory:
        items.append(("excitatory / projection", "arrow"))
    if relations & INHIBITORY_RELATIONS:
        items.append(("inhibitory", "tbar"))
    if relations & MODULATORY_RELATIONS:
        items.append(("modulatory", "dashed"))
    return items


def _append_legend(svg: str, relations: set[EdgeRelation], style: StyleSpec) -> str:
    items = _legend_items(relations)
    if not items:
        return svg
    root = etree.fromstring(svg.encode())
    vb = (root.get("viewBox") or "").replace(",", " ").split()
    if len(vb) != 4:
        return svg
    x0, y0, w, h = (float(v) for v in vb)

    row_h, pad, gap = 18.0, 8.0, 12.0
    legend_h = gap + pad + row_h * len(items) + pad
    new_h = h + legend_h
    root.set("height", f"{new_h:g}pt")
    root.set("viewBox", f"{x0:g} {y0:g} {w:g} {new_h:g}")

    def el(tag: str, **attrs) -> etree._Element:
        e = etree.SubElement(root, f"{{{SVG_NS}}}{tag}")
        for k, v in attrs.items():
            e.set(k.replace("_", "-"), str(v))
        return e

    lx = x0 + 8.0
    top = h + gap + pad
    for i, (label, kind) in enumerate(items):
        cy = top + i * row_h + row_h / 2
        x2 = lx + 26.0
        el(
            "line",
            x1=lx,
            y1=cy,
            x2=x2,
            y2=cy,
            stroke=EDGE_COLOR,
            stroke_width=1.4,
            **({"stroke-dasharray": "5,4"} if kind == "dashed" else {}),
        )
        if kind == "tbar":
            el("line", x1=x2, y1=cy - 6, x2=x2, y2=cy + 6, stroke=EDGE_COLOR, stroke_width=2.0)
        else:
            # filled head = excitatory, open (white) head = modulatory
            el(
                "polygon",
                points=f"{x2},{cy - 4} {x2},{cy + 4} {x2 + 9},{cy}",
                stroke=EDGE_COLOR,
                stroke_width=1.0,
                fill=("#FFFFFF" if kind == "dashed" else EDGE_COLOR),
            )
        t = el(
            "text",
            x=x2 + 16.0,
            y=cy + 4.0,
            fill="#000000",
            font_family=style.font_family,
        )
        t.set("font-size", "11")
        t.text = label
    return etree.tostring(root, xml_declaration=True, encoding="utf-8").decode()


def _dangling_warnings(schema: FigureSchema) -> list[str]:
    return [
        f"Edge references unknown entity: {e.source}->{e.target}" for e in schema.dangling_edges()
    ]
