"""scidraw command-line interface (Typer).

scidraw prompt "M1 projects to spinal cord" --out fig --journal nature
scidraw ingest paper.pdf --section methods --out fig
scidraw lint figure.svg --allow-override no_pie
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .compose import (
    compose_data_plot,
    compose_figure,
    compose_graphical_abstract,
    compose_panels,
    compose_plot_panels,
    compose_scatter,
)
from .config import load_config
from .extract import NeuroDeclineError
from .fetch import AssetFetcher
from .generators.data_plot import DynamitePlotError
from .models import FigureSchema, GraphicalAbstract, PlotRequest, ScatterRequest
from .run import figure_from_file, figure_from_text
from .standards import StyleGuardBlocked, enforce
from .theme import StyleSpec, cohen_lab

app = typer.Typer(add_completion=False, help="Prompt-driven scientific schematic generator.")


def _style(journal: str, allow_override: list[str] | None, style: str = "default") -> StyleSpec:
    """Build a StyleSpec for a journal, optionally on a named house style (e.g. 'cohen')."""
    base = cohen_lab(journal) if style == "cohen" else StyleSpec(journal=journal)
    base.allow_overrides = list(allow_override or [])
    return base


def _export_kwargs(formats: list[str] | None, width: str) -> dict:
    """Translate --format/--width CLI options into compose_* export keyword arguments."""
    fmts = {f.lower() for f in (formats or ["png"])}
    return {
        "export_png": "png" in fmts,
        "export_pdf": "pdf" in fmts,
        "export_eps": "eps" in fmts,
        "export_tiff": "tiff" in fmts,
        "figure_width": width,
    }


def _emit_decline(e: NeuroDeclineError, journal: str) -> None:
    """Print the decline reason, then a ready-to-run render snippet instead of just refusing."""
    from .render_handoff import render_snippet

    typer.secho(str(e), fg=typer.colors.RED)
    handoff = render_snippet(e.matched, style=_style(journal, None))
    typer.secho(
        f"\n# Head start — {handoff.tool} {handoff.kind} render (standards baked in):",
        fg=typer.colors.GREEN,
    )
    for n in handoff.notes:
        typer.secho(f"# - {n}", fg=typer.colors.CYAN)
    typer.echo("\n" + handoff.code)


def _emit(manifest) -> None:
    typer.echo(f"figure: {manifest.svg_path}")
    for r in manifest.raster_paths:
        typer.echo(f"raster: {r}")
    for w in manifest.warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)
    fixes = [a.rule_id for a in manifest.standards.applied_fixes]
    if fixes:
        typer.echo(f"standards applied: {', '.join(fixes)}")
    if manifest.credits.legend_line:
        typer.echo("credits: figure.credits.txt (paste-ready legend line)")
        if manifest.credits.attribution_required:
            typer.secho(
                "  ⚠ contains CC-BY assets — attribution required in the legend.",
                fg=typer.colors.YELLOW,
            )


@app.command()
def prompt(
    text: str,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
) -> None:
    """Generate a figure from a text prompt."""
    try:
        manifest = figure_from_text(
            text, out, config=load_config(), style=_style(journal, allow_override)
        )
    except NeuroDeclineError as e:
        _emit_decline(e, journal)
        raise typer.Exit(code=2) from None
    _emit(manifest)


@app.command()
def ingest(
    path: Path,
    section: str = typer.Option(None, help="'methods' or 'aims' to narrow the source."),
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
) -> None:
    """Generate a figure from a paper/grant file (.pdf/.txt/.md)."""
    try:
        manifest = figure_from_file(
            path, out, config=load_config(), style=_style(journal, allow_override), section=section
        )
    except NeuroDeclineError as e:
        _emit_decline(e, journal)
        raise typer.Exit(code=2) from None
    _emit(manifest)


@app.command()
def plot(
    data_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Render a distribution plot from a PlotRequest JSON ({"groups": {name: [values]}, ...}).

    Enforces distribution rigor (no dynamite bars, geom-by-sample-size, SuperPlots) via the
    same Design Standards Engine. No Claude API call. ``--format`` adds PDF/EPS/TIFF (TIFF is
    CMYK for CMYK journals); ``--width single|double`` sizes to the journal column in mm.
    """
    req = PlotRequest.model_validate_json(data_path.read_text())
    try:
        manifest = compose_data_plot(
            req, out, config=load_config(), style=_style(journal, allow_override),
            **_export_kwargs(fmt, width),
        )
    except DynamitePlotError as e:
        typer.secho(f"BLOCK no_dynamite: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


@app.command()
def scatter(
    data_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    style: str = typer.Option("default", help="House style: 'default' or 'cohen'."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Render a scatter/correlation plot from a ScatterRequest JSON ({"x": [...], "y": [...], ...}).

    With "fit": "linear" an OLS line + 95% band are drawn and Pearson r/p/n are reported. No
    Claude API call. Distribution rigor (text-as-text, floors) is enforced by the same engine.
    """
    req = ScatterRequest.model_validate_json(data_path.read_text())
    manifest = compose_scatter(
        req, out, config=load_config(), style=_style(journal, None, style),
        **_export_kwargs(fmt, width),
    )
    _emit(manifest)


@app.command()
def panels(
    schemas_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
    assets: bool = typer.Option(True, help="Fetch CC assets for anatomical panels."),
    ncols: int = typer.Option(0, help="Grid columns (0 = auto, roughly square)."),
    shared_legend: bool = typer.Option(True, help="Draw one group→colour legend for the figure."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Tile a JSON list of FigureSchema objects into one multi-panel figure (A/B/C ...).

    Panels lay out in a grid (``--ncols``, default ~square). A shared palette keeps each group's
    colour stable across panels and one shared legend is drawn for the figure. No Claude API call.
    """
    raw = json.loads(schemas_path.read_text())
    schemas = [FigureSchema.model_validate(s) for s in raw]
    config = load_config()
    fetcher = AssetFetcher(config) if assets else None
    try:
        manifest = compose_panels(
            schemas, out, config=config, style=_style(journal, allow_override), fetcher=fetcher,
            ncols=ncols or None, shared_legend=shared_legend, **_export_kwargs(fmt, width),
        )
    except StyleGuardBlocked as e:
        for a in e.actions:
            typer.secho(f"BLOCK {a.rule_id}: {a.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


@app.command(name="plot-panels")
def plot_panels(
    data_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    style: str = typer.Option("default", help="House style: 'default' or 'cohen'."),
    shared_y: bool = typer.Option(True, help="Share the y-axis across panels (comparable)."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Tile distribution plots as subplots sharing a y-axis + one shared legend.

    ``data_path`` is a JSON list of PlotRequest objects. A common y-scale makes panels directly
    comparable (box/violin across conditions); the group→colour legend is drawn once. No Claude
    API call. ``--no-shared-y`` gives each panel its own y-axis.
    """
    raw = json.loads(data_path.read_text())
    requests = [PlotRequest.model_validate(r) for r in raw]
    try:
        manifest = compose_plot_panels(
            requests, out, config=load_config(), style=_style(journal, None, style),
            shared_y=shared_y, **_export_kwargs(fmt, width),
        )
    except DynamitePlotError as e:
        typer.secho(f"BLOCK no_dynamite: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


@app.command()
def abstract(
    spec_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    style: str = typer.Option("cohen", help="House style: 'default' or 'cohen'."),
    column: str = typer.Option("half", help="Page width: 'full' | 'half' | 'third'."),
    assets: bool = typer.Option(True, help="Fetch CC assets for unfilled image slots / icons."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Render a grant graphical abstract from a GraphicalAbstract JSON (no Claude API call).

    The design is generated structurally; image slots take your own render paths (preferred)
    or a CC asset_query (fallback) — never an image model. Narrow ``--column`` widths reflow
    multi-item rows to stack vertically. Defaults to the Cohen house style, half-column width.
    """
    ga = GraphicalAbstract.model_validate_json(spec_path.read_text())
    config = load_config()
    fetcher = AssetFetcher(config) if assets else None
    manifest = compose_graphical_abstract(
        ga, out, config=config, style=_style(journal, None, style), fetcher=fetcher,
        column=column, **_export_kwargs(fmt, width),
    )
    _emit(manifest)


@app.command(name="render-snippet")
def render_snippet_cmd(
    text: str,
    journal: str = typer.Option("nature", help="Journal preset (figure size + DPI)."),
    data_kind: str = typer.Option(
        "signed", help="signed (t/z/%-change) | magnitude | cyclic — picks the Crameri map."
    ),
    orientation: str = typer.Option("neurological", help="neurological | radiological."),
    image: str = typer.Option("stat_map.nii.gz", help="Path to your volume/surface."),
) -> None:
    """Emit a standards-baked nilearn / Surf Ice render snippet for a real-data figure.

    For requests the schematic generator must decline (stat maps, glass brain, surface /
    tractography overlays): prints ready-to-run code with a Crameri colormap, sign-preserving
    colorbar, journal figure size at print DPI, and an explicit L/R orientation convention.
    """
    from .models import DataKind
    from .render_handoff import render_snippet

    try:
        dk = DataKind(data_kind)
    except ValueError:
        dk = DataKind.SIGNED
    handoff = render_snippet(
        text, style=_style(journal, None), data_kind=dk, orientation=orientation, image=image
    )
    typer.secho(f"# {handoff.tool} — {handoff.kind} render (standards baked in)", fg="green")
    for n in handoff.notes:
        typer.secho(f"# - {n}", fg="cyan")
    typer.echo()
    typer.echo(handoff.code)


@app.command()
def lint(
    svg_path: Path,
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
) -> None:
    """Run the Design Standards Engine over an SVG and report findings."""
    style = _style(journal, allow_override)
    try:
        _, report = enforce(svg_path.read_text(), style)
    except StyleGuardBlocked as e:
        for a in e.actions:
            typer.secho(f"BLOCK {a.rule_id}: {a.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    for a in report.applied_fixes:
        typer.echo(f"fix {a.rule_id}: {a.message}")
    for a in report.warnings:
        typer.secho(f"warn {a.rule_id}: {a.message}", fg=typer.colors.YELLOW)
    for a in report.overrides:
        typer.secho(f"override {a.rule_id}: {a.message}", fg=typer.colors.CYAN)
    typer.secho("compliant", fg=typer.colors.GREEN)


@app.command(name="compose-schema")
def compose_schema(
    schema_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    style: str = typer.Option("default", help="House style: 'default' or 'cohen'."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
    assets: bool = typer.Option(True, help="Fetch CC assets for anatomical figures."),
    fmt: list[str] = typer.Option(
        None, "--format", help="Export format(s): png pdf eps tiff (repeatable). Default png."
    ),
    width: str = typer.Option("none", help="Physical size: none | single | double (column)."),
) -> None:
    """Render a FigureSchema JSON file to a figure (no Claude API call — subscription mode).

    Author the schema yourself (or have Claude Code author it) and render it locally.
    ``--style cohen`` applies the Cohen-lab house style (outline cards, lab palette).
    """
    config = load_config()
    fig = FigureSchema.model_validate_json(schema_path.read_text())
    fetcher = AssetFetcher(config) if assets else None
    try:
        manifest = compose_figure(
            fig, out, config=config, style=_style(journal, allow_override, style), fetcher=fetcher,
            **_export_kwargs(fmt, width),
        )
    except StyleGuardBlocked as e:
        for a in e.actions:
            typer.secho(f"BLOCK {a.rule_id}: {a.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


if __name__ == "__main__":
    app()
