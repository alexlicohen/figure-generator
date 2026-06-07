"""FastMCP server (stdio) exposing the agent to Claude Code and other MCP clients.

Tools:
- schema_from_text : prompt -> FigureSchema (or a structured neuro-decline redirect)
- find_asset       : license-gated organic asset lookup
- compose_figure   : FigureSchema -> compliant SVG + raster + manifest on disk
- lint_figure      : run the Design Standards Engine over an SVG and report

Register with Claude Code:
    claude mcp add --transport stdio scidraw -- python -m scidraw_agent.mcp_server
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from .compose import compose_figure as _compose_figure
from .config import load_config
from .extract import NeuroDeclineError, extract
from .fetch import AssetFetcher
from .models import FigureSchema
from .run import figure_from_file, figure_from_text
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


@mcp.tool
def schema_from_text(text: str) -> dict:
    """Extract a FigureSchema from a prompt. Declines real neuroimaging-render requests."""
    try:
        schema = extract(text)
    except NeuroDeclineError as e:
        return {"declined": True, "reason": str(e), "matched": e.matched, "use_instead": e.tools}
    return {"declined": False, "schema": schema.model_dump()}


@mcp.tool
def find_asset(query: str) -> dict:
    """Find a CC-compatible organic SVG asset; returns the chosen record + any rejected."""
    result = AssetFetcher().resolve(query)
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
) -> dict:
    """Render a FigureSchema to a compliant figure.svg + raster + manifest in out_dir."""
    style = StyleSpec(journal=journal, allow_overrides=allow_overrides or [])
    config = load_config()
    fig = FigureSchema.model_validate(schema)
    try:
        manifest = _compose_figure(fig, out_dir, config=config, style=style)
    except StyleGuardBlocked as e:
        return {"blocked": [a.model_dump() for a in e.actions]}
    return {
        "svg_path": manifest.svg_path,
        "raster_paths": manifest.raster_paths,
        "warnings": manifest.warnings,
        "standards": _report_dict(manifest.standards),
    }


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


def _manifest_summary(manifest) -> dict:
    return {
        "figure_type": str(manifest.figure_type),
        "svg_path": manifest.svg_path,
        "raster_paths": manifest.raster_paths,
        "assets": [a.model_dump() for a in manifest.assets],
        "warnings": manifest.warnings,
        "standards": _report_dict(manifest.standards),
    }


@mcp.tool
def make_figure(
    text: str,
    out_dir: str,
    journal: str = "nature",
    allow_overrides: list[str] | None = None,
    use_assets: bool = True,
) -> dict:
    """Text -> compliant figure on disk (full pipeline: extract, self-check, compose).

    Declines real neuroimaging-render requests. ``use_assets`` fetches CC-licensed organic
    assets (network) for anatomical figures; set False for offline placeholders.
    """
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
    """Paper/grant file (.pdf/.txt/.md) -> compliant figure on disk.

    ``section`` ('methods' | 'aims') narrows the source; omit to use the whole document.
    """
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
