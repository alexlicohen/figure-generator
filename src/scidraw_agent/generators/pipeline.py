"""Analysis-pipeline and study-design generator (Graphviz `dot` -> SVG).

Graphviz handles layered flow layout (CONSORT-style designs, processing pipelines). Node
fills come from the shared PaletteRegistry; the white background + frame Graphviz emits are
stripped by style_guard downstream. Requires the system `dot` binary (apt: graphviz).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import graphviz

from ..models import FigureSchema, FigureType
from ..palette import PaletteRegistry, parse_color
from ..theme import StyleSpec
from . import GeneratorResult

if TYPE_CHECKING:
    from ..fetch import AssetFetcher


def _font_color(fill: str) -> str:
    rgb = parse_color(fill) or (0, 0, 0)
    return "black" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 140 else "white"


class PipelineGenerator:
    figure_types = {FigureType.ANALYSIS_PIPELINE, FigureType.STUDY_DESIGN}

    def generate(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
        *,
        fetcher: AssetFetcher | None = None,
    ) -> GeneratorResult:
        outline = getattr(style, "node_style", "filled") == "outline"
        ink = getattr(style, "node_ink", "#333333")
        g = graphviz.Digraph("figure")
        g.attr(rankdir="TB", bgcolor="white", nodesep="0.35", ranksep="0.5")
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
            "edge", color=ink, arrowsize="0.8", penwidth="1.2", fontname="Arial", fontsize="11"
        )

        for e in schema.entities:
            accent = palette.assign(e.group or e.id).color
            if outline:
                # white card, coloured outline, ink text — the lab's white-box look, elevated
                g.node(e.id, e.label, fillcolor="white", color=accent, fontcolor=ink)
            else:
                g.node(e.id, e.label, fillcolor=accent, fontcolor=_font_color(accent))

        for edge in schema.edges:
            if edge.source in schema.entity_ids() and edge.target in schema.entity_ids():
                g.edge(edge.source, edge.target, label=edge.label or "")

        svg = g.pipe(format="svg").decode("utf-8")
        warnings = [
            f"Edge references unknown entity: {e.source}->{e.target}"
            for e in schema.dangling_edges()
        ]
        return GeneratorResult(svg=svg, warnings=warnings)
