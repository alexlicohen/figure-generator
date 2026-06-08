"""scidraw command-line interface (Typer).

scidraw prompt "M1 projects to spinal cord" --out fig --journal nature
scidraw ingest paper.pdf --section methods --out fig
scidraw lint figure.svg --allow-override no_pie
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .compose import compose_data_plot, compose_figure, compose_panels
from .config import load_config
from .extract import NeuroDeclineError
from .fetch import AssetFetcher
from .generators.data_plot import DynamitePlotError
from .models import FigureSchema, PlotRequest
from .run import figure_from_file, figure_from_text
from .standards import StyleGuardBlocked, enforce
from .theme import StyleSpec

app = typer.Typer(add_completion=False, help="Prompt-driven scientific schematic generator.")


def _style(journal: str, allow_override: list[str] | None) -> StyleSpec:
    return StyleSpec(journal=journal, allow_overrides=list(allow_override or []))


def _emit(manifest) -> None:
    typer.echo(f"figure: {manifest.svg_path}")
    for r in manifest.raster_paths:
        typer.echo(f"raster: {r}")
    for w in manifest.warnings:
        typer.secho(f"warning: {w}", fg=typer.colors.YELLOW)
    fixes = [a.rule_id for a in manifest.standards.applied_fixes]
    if fixes:
        typer.echo(f"standards applied: {', '.join(fixes)}")


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
        typer.secho(str(e), fg=typer.colors.RED)
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
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(code=2) from None
    _emit(manifest)


@app.command()
def plot(
    data_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
) -> None:
    """Render a distribution plot from a PlotRequest JSON ({"groups": {name: [values]}, ...}).

    Enforces distribution rigor (no dynamite bars, geom-by-sample-size, SuperPlots) via the
    same Design Standards Engine. No Claude API call.
    """
    req = PlotRequest.model_validate_json(data_path.read_text())
    try:
        manifest = compose_data_plot(
            req, out, config=load_config(), style=_style(journal, allow_override)
        )
    except DynamitePlotError as e:
        typer.secho(f"BLOCK no_dynamite: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


@app.command()
def panels(
    schemas_path: Path,
    out: Path = typer.Option(Path("figure_out"), help="Output directory."),
    journal: str = typer.Option("nature", help="Journal preset."),
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
    assets: bool = typer.Option(True, help="Fetch CC assets for anatomical panels."),
) -> None:
    """Tile a JSON list of FigureSchema objects into one multi-panel figure (A/B/C ...).

    A shared palette keeps each group's colour stable across panels. No Claude API call.
    """
    raw = json.loads(schemas_path.read_text())
    schemas = [FigureSchema.model_validate(s) for s in raw]
    config = load_config()
    fetcher = AssetFetcher(config) if assets else None
    try:
        manifest = compose_panels(
            schemas, out, config=config, style=_style(journal, allow_override), fetcher=fetcher
        )
    except StyleGuardBlocked as e:
        for a in e.actions:
            typer.secho(f"BLOCK {a.rule_id}: {a.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


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
    allow_override: list[str] = typer.Option(None, help="BLOCK rule id(s) to override."),
    assets: bool = typer.Option(True, help="Fetch CC assets for anatomical figures."),
) -> None:
    """Render a FigureSchema JSON file to a figure (no Claude API call — subscription mode).

    Author the schema yourself (or have Claude Code author it) and render it locally.
    """
    config = load_config()
    fig = FigureSchema.model_validate_json(schema_path.read_text())
    fetcher = AssetFetcher(config) if assets else None
    try:
        manifest = compose_figure(
            fig, out, config=config, style=_style(journal, allow_override), fetcher=fetcher
        )
    except StyleGuardBlocked as e:
        for a in e.actions:
            typer.secho(f"BLOCK {a.rule_id}: {a.message}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    _emit(manifest)


if __name__ == "__main__":
    app()
