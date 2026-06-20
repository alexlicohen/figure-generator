"""Analysis-pipeline, study-design, and reporting-flow generator (Graphviz `dot` -> SVG).

Graphviz handles layered flow layout (CONSORT-style designs, processing pipelines, and the
reporting-guideline participant-flow diagrams — CONSORT/PRISMA/STROBE/STARD). Node fills come
from the shared PaletteRegistry; the white background + frame Graphviz emits are stripped by
style_guard downstream. Requires the system `dot` binary (apt: graphviz).

Reporting flows add three general schema flags this generator honours:
  * ``Entity.side_box`` — drawn as a light ``note``-shaped annotation (exclusion-reason box),
    not a saturated spine node.
  * ``Entity.rank_with`` — placed on the same horizontal rank as the named spine node
    (Graphviz ``rank=same`` subgraph), so an exclusion box sits *beside* its branch point.
  * ``Edge.style`` / ``Edge.arrow`` / ``Edge.constraint`` — a dashed, arrowless,
    ``constraint=false`` connector is the exclusion-cascade side branch (it must not push the
    layout down a level). These are general edge attributes, not PRISMA-hardcoded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import graphviz

from ..models import FigureSchema, FigureType
from ..palette import PaletteRegistry, parse_color, shade_ramp
from ..theme import StyleSpec
from . import GeneratorResult

if TYPE_CHECKING:
    from ..fetch import AssetFetcher


def _font_color(fill: str) -> str:
    rgb = parse_color(fill) or (0, 0, 0)
    return "black" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 140 else "white"


class PipelineGenerator:
    figure_types = {
        FigureType.ANALYSIS_PIPELINE,
        FigureType.STUDY_DESIGN,
        FigureType.REPORTING_FLOW,
    }

    def generate(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
        *,
        fetcher: AssetFetcher | None = None,
    ) -> GeneratorResult:
        g = self.build_dot(schema, style, palette)
        svg = g.pipe(format="svg").decode("utf-8")
        warnings = [
            f"Edge references unknown entity: {e.source}->{e.target}"
            for e in schema.dangling_edges()
        ]
        return GeneratorResult(svg=svg, warnings=warnings)

    def build_dot(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
    ) -> graphviz.Digraph:
        """Build the Graphviz ``Digraph`` for a schema (layout only; not yet rendered to SVG).

        Exposed so the side-box / exclusion-cascade dot attributes (``style=dashed``,
        ``dir=none``, ``constraint=false``, ``rank=same``, ``shape=note``) can be asserted
        directly at the dot layer.
        """
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

        # A *sequential* pipeline with no groups reads as a rainbow if each step gets the next
        # categorical hue. Shade one hue by position instead (light->dark = progression). Keep
        # the categorical/group mapping for study designs (cohorts/arms) and any grouped figure.
        # Reporting flows are not a single progression (they branch), so they keep flat,
        # neutral spine boxes (see _flow_node) rather than the ramp.
        sequential = schema.figure_type == FigureType.ANALYSIS_PIPELINE and all(
            e.group is None for e in schema.entities
        )
        ramp = (
            shade_ramp(style.categorical[0], len(schema.entities))
            if sequential and style.categorical
            else None
        )

        for i, e in enumerate(schema.entities):
            if getattr(e, "side_box", False):
                self._side_box_node(g, e, style, ink)
                continue
            if schema.figure_type == FigureType.REPORTING_FLOW:
                self._flow_node(g, e, style, palette, ink, outline)
                continue
            accent = ramp[i] if ramp else palette.assign(e.group or e.id).color
            if outline:
                # white card, coloured outline, ink text — the lab's white-box look, elevated
                g.node(e.id, e.label, fillcolor="white", color=accent, fontcolor=ink)
            else:
                g.node(e.id, e.label, fillcolor=accent, fontcolor=_font_color(accent))

        # rank=same: keep each side-box level with the spine node it branches off, so the
        # exclusion-reason annotation sits *beside* the branch point, not a row below it.
        ids = schema.entity_ids()
        for e in schema.entities:
            peer = getattr(e, "rank_with", None)
            if peer and peer in ids and e.id in ids:
                with g.subgraph() as s:
                    s.attr(rank="same")
                    s.node(peer)
                    s.node(e.id)

        for edge in schema.edges:
            if edge.source in ids and edge.target in ids:
                g.edge(edge.source, edge.target, label=edge.label or "", **_edge_attrs(edge))

        return g

    # -- reporting-flow node rendering ------------------------------------- #
    @staticmethod
    def _flow_node(g, e, style: StyleSpec, palette: PaletteRegistry, ink: str, outline: bool):
        """A spine box in a reporting flow. Highlight boxes (analytic cohort / randomized /
        included) carry an accent fill; the rest are clean neutral cards so the eye follows
        the spine and counts, not a rainbow of step colours."""
        if getattr(e, "highlight", False):
            accent = palette.assign(e.group or "_flow_highlight").color
            if outline:
                g.node(
                    e.id, e.label,
                    fillcolor="white", color=accent, fontcolor=ink, penwidth="2.4",
                )
            else:
                g.node(e.id, e.label, fillcolor=accent, fontcolor=_font_color(accent))
        else:
            g.node(e.id, e.label, fillcolor="white", color=ink, fontcolor=ink)

    @staticmethod
    def _side_box_node(g, e, style: StyleSpec, ink: str):
        """An exclusion-reason annotation: Graphviz ``note`` shape, no rounded fill, smaller
        font — visually subordinate to the spine (matches CONSORT/PRISMA/STROBE/STARD)."""
        g.node(
            e.id,
            e.label,
            shape="note",
            style="filled",
            fillcolor="#F5F5F5",
            color=ink,
            fontcolor=ink,
            fontsize="10",
        )


def _edge_attrs(edge) -> dict[str, str]:
    """Translate the general Edge flow flags into Graphviz edge attributes.

    A dashed + arrowless + ``constraint=false`` edge is the exclusion-cascade side branch:
    it connects a spine node to its side-box without adding a flow arrow or pushing the
    layout down a rank.
    """
    attrs: dict[str, str] = {}
    if getattr(edge, "style", "solid") == "dashed":
        attrs["style"] = "dashed"
    if not getattr(edge, "arrow", True):
        attrs["dir"] = "none"
    if not getattr(edge, "constraint", True):
        attrs["constraint"] = "false"
    return attrs
