"""FastMCP server (stdio) exposing the agent to Claude Code and other MCP clients.

Two ways to use it:

**Subscription mode (no ANTHROPIC_API_KEY).** Claude Code itself authors the FigureSchema
(billed to your Claude subscription) and calls only the LOCAL tools below to validate and
render. Nothing here calls the Anthropic API.
    check_decline · self_check · compose_figure · find_asset · lint_figure · list_rules

**API mode (needs ANTHROPIC_API_KEY).** The package makes its own Claude call to extract a
schema — for non-interactive / scripted use.
    schema_from_text · make_figure · make_figure_from_file

Register with Claude Code:
    claude mcp add scidraw -- uv run python -m scidraw_agent.mcp_server
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP
from pydantic import ValidationError

from .compose import compose_data_plot as _compose_data_plot
from .compose import compose_figure as _compose_figure
from .compose import compose_panels as _compose_panels
from .compose import compose_plot_panels as _compose_plot_panels
from .compose import compose_scatter as _compose_scatter
from .config import load_config
from .extract import NeuroDeclineError, extract, neuro_decline_trigger
from .fetch import AssetFetcher
from .generators.data_plot import DynamitePlotError
from .models import FigureSchema, PlotRequest, ScatterRequest
from .run import figure_from_file, figure_from_text
from .selfcheck import brain_panels_missing_orientation, invented_entities
from .standards import StyleGuardBlocked, enforce
from .standards.linter import RULES
from .theme import StyleSpec

mcp = FastMCP("scidraw-agent")


def _report_dict(report) -> dict:
    return {
        "applied_fixes": [a.model_dump() for a in report.applied_fixes],
        "warnings": [a.model_dump() for a in report.warnings],
        "overrides": [a.model_dump() for a in report.overrides],
    }


def _export_kwargs(formats: list[str] | None, figure_width: str) -> dict:
    """Translate a formats list + width into compose_* export keyword arguments."""
    fmts = {f.lower() for f in (formats or ["png"])}
    return {
        "export_png": "png" in fmts,
        "export_pdf": "pdf" in fmts,
        "export_eps": "eps" in fmts,
        "export_tiff": "tiff" in fmts,
        "figure_width": figure_width,
    }


def _manifest_summary(manifest) -> dict:
    return {
        "figure_type": str(manifest.figure_type),
        "svg_path": manifest.svg_path,
        "raster_paths": manifest.raster_paths,
        "assets": [a.model_dump() for a in manifest.assets],
        "warnings": manifest.warnings,
        "standards": _report_dict(manifest.standards),
        "credits": manifest.credits.model_dump(),
    }


# ===================================================================== #
# LOCAL tools — no Anthropic API call (usable in subscription mode)
# ===================================================================== #
@mcp.tool
def check_decline(
    text: str,
    journal: str = "nature",
    data_kind: str = "signed",
    orientation: str = "neurological",
) -> dict:
    """Neuro-decline gate (local, no API). Run BEFORE authoring a schema.

    If a request asks for a real neuroimaging render (voxel/stat-map/tractography/surface
    overlay), returns declined=True — do NOT draw a schematic. Instead of a bare tool list it
    returns a ``handoff``: ready-to-run nilearn/Surf Ice code with the standards baked in
    (Crameri colormap by ``data_kind``, sign-preserving colorbar, journal figure size at print
    DPI, explicit L/R ``orientation``). ``data_kind`` is signed (t/z/%-change) | magnitude |
    cyclic; ``orientation`` is neurological | radiological.
    """
    from .models import DataKind
    from .render_handoff import render_snippet
    from .theme import StyleSpec as _Style

    matched = neuro_decline_trigger(text)
    if not matched:
        return {"declined": False}
    try:
        dk = DataKind(data_kind)
    except ValueError:
        dk = DataKind.SIGNED
    handoff = render_snippet(
        text, style=_Style(journal=journal), data_kind=dk, orientation=orientation
    )
    return {
        "declined": True,
        "matched": matched,
        "use_instead": [
            "nilearn (plot_stat_map / plot_glass_brain)",
            "FSLeyes",
            "MRIcroGL",
            "Surf Ice",
        ],
        "handoff": {
            "kind": str(handoff.kind),
            "tool": handoff.tool,
            "code": handoff.code,
            "notes": handoff.notes,
        },
    }


@mcp.tool
def self_check(schema: dict, source_text: str = "") -> dict:
    """Validate a FigureSchema + flag invented entities / missing brain orientation (local).

    ``source_text`` is the prompt/Methods text the schema came from; when given, entities
    whose words don't appear in it are flagged as possibly invented (never invent anatomy).
    """
    try:
        fig = FigureSchema.model_validate(schema)
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    warnings: list[str] = []
    if source_text:
        warnings += [
            f"possible invented entity not in source: '{x}'"
            for x in invented_entities(source_text, fig)
        ]
    warnings += [
        f"brain slice '{x}' lacks orientation/L-R declaration"
        for x in brain_panels_missing_orientation(fig)
    ]
    warnings += [
        f"edge references unknown entity: {e.source}->{e.target}" for e in fig.dangling_edges()
    ]
    return {"valid": True, "warnings": warnings}


@mcp.tool
def find_asset(query: str) -> dict:
    """Find a CC-compatible organic SVG asset (local network to Zenodo/bioicons; no API)."""
    result = AssetFetcher(load_config()).resolve(query)
    return {
        "record": result.record.model_dump() if result.record else None,
        "rejected": [r.model_dump() for r in result.rejected],
        "n_candidates": len(result.candidates),
    }


@mcp.tool
def compose_figure(
    schema: dict,
    out_dir: str,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    use_assets: bool = True,
    house_style: str = "default",
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Render a FigureSchema -> compliant figure.svg + raster + manifest (local, no API).

    This is the subscription-mode render entry point: you (Claude Code) supply the schema.
    ``use_assets`` fetches CC-licensed organic assets for anatomical figures.
    ``house_style="cohen"`` applies the Cohen-lab look (outline cards, lab palette, grey assets).
    ``formats`` ⊆ ["png","pdf","eps","tiff"] (default png; TIFF is CMYK for CMYK journals);
    ``figure_width`` ∈ none|single|double sizes the figure to the journal column width in mm.
    """
    from .theme import cohen_lab

    style = cohen_lab(journal) if house_style == "cohen" else StyleSpec(journal=journal)
    style.allow_overrides = allow_overrides or []
    config = load_config()
    fetcher = AssetFetcher(config) if use_assets else None
    try:
        fig = FigureSchema.model_validate(schema)
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    try:
        manifest = _compose_figure(
            fig, out_dir, config=config, style=style, fetcher=fetcher,
            **_export_kwargs(formats, figure_width),
        )
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions]}
    return _manifest_summary(manifest)


@mcp.tool
def make_data_plot(
    request: dict,
    out_dir: str,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Render a distribution plot -> compliant figure.svg + raster + manifest (local, no API).

    ``request`` is a PlotRequest: {"groups": {name: [values]}, optional "replicates",
    "xlabel", "ylabel", "title", "force_kind"}. Distribution rigor is enforced (no dynamite
    bars, geom-by-sample-size, SuperPlots for nested replicates). force_kind="bar" is blocked
    unless ``no_dynamite`` is in allow_overrides.

    Set "annotate_stats": true to draw significance brackets between groups (stars on the plot;
    exact p, n and effect size recorded in the manifest for the legend). "comparisons" picks the
    pairs ([["A","B"], ...], default adjacent); "paired"/"parametric" choose the test.
    """
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    try:
        req = PlotRequest.model_validate(request)
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    try:
        manifest = _compose_data_plot(
            req, out_dir, config=load_config(), style=style,
            **_export_kwargs(formats, figure_width),
        )
    except DynamitePlotError as e:
        return {"blocked": [{"rule_id": "no_dynamite", "message": str(e)}]}
    return _manifest_summary(manifest)


@mcp.tool
def make_scatter_plot(
    request: dict,
    out_dir: str,
    journal: str = "nature",
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Render a scatter/correlation plot -> compliant SVG + raster + manifest (local, no API).

    ``request`` is a ScatterRequest: {"x": [...], "y": [...], optional "groups" (per-point label
    for colour), "xlabel", "ylabel", "title", "fit" ("linear"|"none"), "annotate_stats"}. With a
    linear fit, an OLS line + 95% band are drawn and Pearson r/p/n are reported in the manifest's
    standards (STAT_REPORTING) for paste-ready legends.
    """
    style = StyleSpec(journal=journal)
    try:
        req = ScatterRequest.model_validate(request)
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    manifest = _compose_scatter(
        req, out_dir, config=load_config(), style=style,
        **_export_kwargs(formats, figure_width),
    )
    return _manifest_summary(manifest)


@mcp.tool
def make_graphical_abstract(
    spec: dict,
    out_dir: str,
    journal: str = "nature",
    house_style: str = "cohen",
    column: str = "half",
    use_assets: bool = True,
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Render a grant graphical abstract from a GraphicalAbstract spec (local, no API).

    The composition (sections of cards / tracks / image slots / grids, connectors, colour
    system, icons) is generated structurally — NOT an image model. Image slots take a real
    render ``path`` (preferred) or a CC ``asset_query`` fallback. ``column`` ("full" | "half" |
    "third") sets the page width; narrow widths reflow rows to stack. Defaults to Cohen style.
    """
    from .compose import compose_graphical_abstract as _compose_ga
    from .models import GraphicalAbstract
    from .theme import cohen_lab

    style = cohen_lab(journal) if house_style == "cohen" else StyleSpec(journal=journal)
    config = load_config()
    fetcher = AssetFetcher(config) if use_assets else None
    try:
        ga = GraphicalAbstract.model_validate(spec)
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    manifest = _compose_ga(
        ga, out_dir, config=config, style=style, fetcher=fetcher, column=column,
        **_export_kwargs(formats, figure_width),
    )
    return _manifest_summary(manifest)


@mcp.tool
def compose_panels_figure(
    schemas: list[dict],
    out_dir: str,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    use_assets: bool = True,
    ncols: int = 0,
    shared_legend: bool = True,
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Tile multiple FigureSchemas into one multi-panel figure (A/B/C ...) (local, no API).

    Panels lay out in a grid (``ncols``; 0 = auto, ~square). A shared palette keeps each group's
    colour stable across panels and ``shared_legend`` draws one group→colour legend for the
    figure. ``use_assets`` fetches CC-licensed organic assets for anatomical panels.
    """
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    config = load_config()
    fetcher = AssetFetcher(config) if use_assets else None
    try:
        figs = [FigureSchema.model_validate(s) for s in schemas]
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    try:
        manifest = _compose_panels(
            figs, out_dir, config=config, style=style, fetcher=fetcher,
            ncols=ncols or None, shared_legend=shared_legend,
            **_export_kwargs(formats, figure_width),
        )
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions]}
    return _manifest_summary(manifest)


@mcp.tool
def compose_plot_panels_figure(
    requests: list[dict],
    out_dir: str,
    journal: str = "nature",
    shared_y: bool = True,
    formats: list[str] | None = None,
    figure_width: str = "none",
) -> dict:
    """Tile distribution plots as subplots sharing a y-axis + one shared legend (local, no API).

    ``requests`` is a list of PlotRequest dicts. A common y-scale makes the panels directly
    comparable (box/violin across conditions) and the group→colour legend is drawn once. Same
    distribution rigor as make_data_plot per panel; force_kind="bar" blocks without override.
    """
    style = StyleSpec(journal=journal)
    try:
        reqs = [PlotRequest.model_validate(r) for r in requests]
    except ValidationError as e:
        return {"valid": False, "errors": e.errors(include_url=False)}
    try:
        manifest = _compose_plot_panels(
            reqs, out_dir, config=load_config(), style=style, shared_y=shared_y,
            **_export_kwargs(formats, figure_width),
        )
    except DynamitePlotError as e:
        return {"blocked": [{"rule_id": "no_dynamite", "message": str(e)}]}
    return _manifest_summary(manifest)


@mcp.tool
def lint_figure(
    svg: str, journal: str = "nature", allow_overrides: list[str] | None = None
) -> dict:
    """Run the Design Standards Engine over an SVG string (or file path); return the report."""
    candidate = Path(svg)
    if len(svg) < 400 and candidate.exists():
        svg = candidate.read_text()
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    try:
        _, report = enforce(svg, style)
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions], "report": _report_dict(e.report)}
    return {"blocked": [], "report": _report_dict(report)}


@mcp.tool
def list_rules() -> dict:
    """List the design-standards rule catalog (id -> tier, message, source)."""
    return {
        str(rid): {"tier": r.tier, "message": r.message, "source_url": r.source_url}
        for rid, r in RULES.items()
    }


# ===================================================================== #
# API tools — make their own Anthropic call (need ANTHROPIC_API_KEY)
# ===================================================================== #
@mcp.tool
def schema_from_text(text: str) -> dict:
    """[API] Extract a FigureSchema from a prompt. Declines real neuroimaging-render requests."""
    try:
        schema = extract(text)
    except NeuroDeclineError as e:
        return {"declined": True, "reason": str(e), "matched": e.matched, "use_instead": e.tools}
    return {"declined": False, "schema": schema.model_dump()}


@mcp.tool
def make_figure(
    text: str,
    out_dir: str,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    use_assets: bool = True,
) -> dict:
    """[API] Text -> compliant figure on disk (full pipeline: extract, self-check, compose)."""
    config = load_config()
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    fetcher = AssetFetcher(config) if use_assets else None
    try:
        manifest = figure_from_text(text, out_dir, config=config, style=style, fetcher=fetcher)
    except NeuroDeclineError as e:
        return {"declined": True, "reason": str(e), "matched": e.matched, "use_instead": e.tools}
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions]}
    return _manifest_summary(manifest)


@mcp.tool
def make_figure_from_file(
    path: str,
    out_dir: str,
    section: str | None = None,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    use_assets: bool = True,
) -> dict:
    """[API] Paper/grant file (.pdf/.txt/.md) -> compliant figure on disk."""
    config = load_config()
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    fetcher = AssetFetcher(config) if use_assets else None
    try:
        manifest = figure_from_file(
            path, out_dir, config=config, style=style, fetcher=fetcher, section=section
        )
    except NeuroDeclineError as e:
        return {"declined": True, "reason": str(e), "matched": e.matched, "use_instead": e.tools}
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions]}
    return _manifest_summary(manifest)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
