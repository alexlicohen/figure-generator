"""Assemble generator output into a compliant figure + manifest.

Every generator's SVG is run through `style_guard.enforce` before anything is written, so
the figure on disk is guaranteed compliant. Raster export (cairosvg) inherits the guarded
SVG, so PNG/PDF carry the same stroke/font floors. The manifest records license provenance
(per asset) and standards provenance (applied fixes / overrides / warnings).
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .config import Config, load_config
from .models import (
    Credits,
    FigureSchema,
    FigureType,
    GraphicalAbstract,
    Manifest,
    PlotRequest,
    ScatterRequest,
    StandardsReport,
)
from .palette import PaletteRegistry
from .router import route
from .standards import enforce
from .theme import StyleSpec

SVG_NS = "http://www.w3.org/2000/svg"


def _viewport(svg: str) -> tuple[float, float]:
    root = etree.fromstring(svg.encode())
    vb = root.get("viewBox")
    if vb:
        p = vb.replace(",", " ").split()
        if len(p) == 4:
            return float(p[2]), float(p[3])
    import re

    def num(v):
        m = re.match(r"[\d.]+", v or "")
        return float(m.group()) if m else 0.0

    return num(root.get("width")), num(root.get("height"))


def _shared_legend_group(palette, x0: float, y0: float, max_w: float, style):
    """Build one figure-level group→colour legend (swatch + label), wrapping to ``max_w``.

    Returns (lxml <g> element, height) — or (None, 0) when fewer than two groups appeared, so
    a single-group figure isn't given a redundant legend.
    """
    groups = list(palette.mapping.items())
    if len(groups) < 2:
        return None, 0.0
    ns = "{http://www.w3.org/2000/svg}"
    g = etree.Element(f"{ns}g")
    g.set("class", "panel-legend")
    sw, pad, gap_x = 14.0, 6.0, 24.0
    fs = style.default_font_px
    x, y, row_h = x0, y0, fs + 10
    for name, gstyle in groups:
        label_w = sw + pad + 0.62 * fs * len(name) + gap_x
        if x > x0 and x + label_w > x0 + max_w:
            x, y = x0, y + row_h
        rect = etree.SubElement(g, f"{ns}rect")
        rect.set("x", f"{x:g}")
        rect.set("y", f"{y:g}")
        rect.set("width", f"{sw:g}")
        rect.set("height", f"{sw:g}")
        rect.set("rx", "2")
        rect.set("fill", gstyle.color)
        text = etree.SubElement(g, f"{ns}text")
        text.set("x", f"{x + sw + pad:g}")
        text.set("y", f"{y + sw * 0.82:g}")
        text.set("font-size", f"{fs:g}")
        text.set("font-family", style.font_family)
        text.set("fill", style.node_ink)
        text.text = name
        x += label_w
    return g, (y - y0) + row_h


def _write_credits(out_dir: Path, assets: list) -> Credits:
    """Build paste-ready attribution, write figure.credits.txt, and return it for the manifest."""
    from .attribution import build_credits, credits_text

    credits = build_credits(assets)
    (out_dir / "figure.credits.txt").write_text(credits_text(credits))
    return credits


def _export_raster(
    svg: str,
    out_dir: Path,
    style: StyleSpec,
    *,
    png: bool = True,
    pdf: bool = False,
    eps: bool = False,
    tiff: bool = False,
    figure_width: str = "none",
) -> tuple[list[str], list[str]]:
    """Best-effort multi-format export (see :mod:`export`). SVG is the primary deliverable, so
    a missing/unloadable cairo never fails a run — it is recorded as a warning and the SVG
    still ships. ``figure_width`` ∈ {none, single, double} sizes to journal column width.
    """
    from .export import export_artifacts

    formats = [n for flag, n in ((png, "png"), (pdf, "pdf"), (eps, "eps"), (tiff, "tiff")) if flag]
    return export_artifacts(svg, out_dir, style, formats=formats, figure_width=figure_width)


def compose_figure(
    schema: FigureSchema,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    fetcher=None,
    palette: PaletteRegistry | None = None,
    extra_warnings: list[str] | None = None,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Generate, enforce standards, export, and write figure.svg + figure.manifest.json."""
    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry(colors=list(style.categorical))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = route(schema.figure_type).generate(schema, style, palette, fetcher=fetcher)
    cleaned, report = enforce(result.svg, style, data_kind=schema.data_kind)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters, raster_warnings = _export_raster(
        cleaned, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=schema.figure_type,
        caption_seed=schema.caption_seed,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        assets=result.assets,
        standards=report,
        credits=_write_credits(out_dir, result.assets),
        warnings=result.warnings + (extra_warnings or []) + raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def compose_panels(
    schemas: list[FigureSchema],
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    fetcher=None,
    palette: PaletteRegistry | None = None,
    ncols: int | None = None,
    shared_legend: bool = True,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Tile multiple figures into one multi-panel SVG with A/B/C letters.

    Panels are laid out in a grid (``ncols``; defaults to roughly square), not a single row.
    One shared PaletteRegistry is used across panels, so a group keeps the same colour in every
    panel; when ``shared_legend`` and >=2 groups appear, one group->colour legend is drawn for
    the whole figure (instead of repeating per panel).
    """
    from svgutils import transform as st

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry(colors=list(style.categorical))  # shared across panels
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    panels: list[str] = []
    all_assets, all_warnings = [], []
    report_total = None
    for schema in schemas:
        result = route(schema.figure_type).generate(schema, style, palette, fetcher=fetcher)
        cleaned, report = enforce(result.svg, style, data_kind=schema.data_kind)
        panels.append(cleaned)
        all_assets.extend(result.assets)
        all_warnings.extend(result.warnings)
        if report_total is None:
            report_total = report
        else:
            report_total.applied_fixes.extend(report.applied_fixes)
            report_total.warnings.extend(report.warnings)
            report_total.overrides.extend(report.overrides)

    import math

    letter_gap, gap, top, left = 22.0, 36.0, 6.0, 6.0
    n = len(panels)
    cols = ncols or max(1, min(n, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)
    dims = [_viewport(s) for s in panels]
    col_w = [0.0] * cols
    row_h = [0.0] * rows
    for i, (w, h) in enumerate(dims):
        r, c = divmod(i, cols)
        col_w[c] = max(col_w[c], w)
        row_h[r] = max(row_h[r], h)
    col_x, acc = [], left
    for c in range(cols):
        col_x.append(acc)
        acc += col_w[c] + gap
    row_top, acc = [], top
    for r in range(rows):
        acc += letter_gap
        row_top.append(acc)
        acc += row_h[r] + gap

    elements = []
    for i, svg in enumerate(panels):
        r, c = divmod(i, cols)
        root = st.fromstring(svg).getroot()
        root.moveto(col_x[c], row_top[r])
        elements.append(root)
        elements.append(
            st.TextElement(
                col_x[c] + 2, row_top[r] - 6, chr(ord("A") + i),
                size=16, weight="bold", font="Arial",
            )
        )

    grid_w = max(1.0, (col_x[-1] + col_w[-1]))
    last_r = (n - 1) // cols
    grid_bottom = row_top[last_r] + row_h[last_r]

    base = st.SVGFigure(f"{grid_w}px", f"{grid_bottom + 6}px")
    base.append(elements)
    root = etree.fromstring(base.to_str())

    total_w, total_h = grid_w, grid_bottom + 6
    if shared_legend:
        legend, lh = _shared_legend_group(palette, left, grid_bottom + gap * 0.5, grid_w, style)
        if legend is not None:
            root.append(legend)
            total_w = max(total_w, grid_w)
            total_h = grid_bottom + gap * 0.5 + lh + 6
    root.set("width", f"{total_w:g}")
    root.set("height", f"{total_h:g}")
    root.set("viewBox", f"0 0 {total_w:g} {total_h:g}")
    combined, report_final = enforce(etree.tostring(root).decode(), style)
    if report_total is not None:
        report_total.applied_fixes.extend(report_final.applied_fixes)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(combined)
    rasters, raster_warnings = _export_raster(
        combined, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=schemas[0].figure_type,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        assets=all_assets,
        standards=report_total or enforce("<svg/>", style)[1],
        credits=_write_credits(out_dir, all_assets),
        warnings=all_warnings + raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def compose_data_plot(
    request: PlotRequest,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    palette: PaletteRegistry | None = None,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Render a distribution plot (M8 data_plot) -> compliant SVG + raster + manifest.

    Raises DynamitePlotError if a bar+SEM plot is requested without the override.
    """
    from .generators.data_plot import build_distribution_svg

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry(colors=list(style.categorical))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg, actions = build_distribution_svg(request, style, palette)
    report = StandardsReport()
    for a in actions:
        report.add(a)
    cleaned, report = enforce(svg, style, report=report)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters, raster_warnings = _export_raster(
        cleaned, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=FigureType.DATA_PLOT,
        caption_seed=request.title,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        standards=report,
        warnings=raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def compose_plot_panels(
    requests: list[PlotRequest],
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    palette: PaletteRegistry | None = None,
    shared_y: bool = True,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Tile distribution plots as subplots sharing a y-axis + one shared legend (local, no API).

    A shared y-scale makes the panels directly comparable; the group→colour legend is drawn
    once; a shared PaletteRegistry keeps group colours stable. Raises DynamitePlotError if any
    panel forces a bar+SEM plot without the override.
    """
    from .generators.data_plot import build_distribution_panels_svg

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry(colors=list(style.categorical))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg, actions = build_distribution_panels_svg(requests, style, palette, shared_y=shared_y)
    report = StandardsReport()
    for a in actions:
        report.add(a)
    cleaned, report = enforce(svg, style, report=report)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters, raster_warnings = _export_raster(
        cleaned, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=FigureType.DATA_PLOT,
        caption_seed=requests[0].title if requests else "",
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        standards=report,
        warnings=raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def compose_scatter(
    request: ScatterRequest,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    palette: PaletteRegistry | None = None,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Render a scatter/correlation plot (OLS fit + 95% band + r/p/n) -> SVG + raster + manifest."""
    from .generators.data_plot import build_scatter_svg

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry(colors=list(style.categorical))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg, actions = build_scatter_svg(request, style, palette)
    report = StandardsReport()
    for a in actions:
        report.add(a)
    cleaned, report = enforce(svg, style, report=report)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters, raster_warnings = _export_raster(
        cleaned, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=FigureType.DATA_PLOT,
        caption_seed=request.title,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        standards=report,
        warnings=raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest


def compose_graphical_abstract(
    ga: GraphicalAbstract,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    fetcher=None,
    column: str | None = None,
    export_png: bool = True,
    export_pdf: bool = False,
    export_eps: bool = False,
    export_tiff: bool = False,
    figure_width: str = "none",
) -> Manifest:
    """Render a structural graphical abstract -> compliant SVG + raster + manifest + credits.

    The composition is generated; images are slotted from real renders / CC assets (never an
    image model). CC-fetched assets carry their licence into the manifest + figure.credits.txt.
    ``column`` ("full" | "half" | "third") overrides the abstract's page-column width.
    """
    from .generators.graphical_abstract import build_graphical_abstract_svg

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    if column:
        ga.column, ga.width = column, 0.0
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg, assets, warnings = build_graphical_abstract_svg(ga, style, fetcher)
    cleaned, report = enforce(svg, style)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters, raster_warnings = _export_raster(
        cleaned, out_dir, style, png=export_png, pdf=export_pdf,
        eps=export_eps, tiff=export_tiff, figure_width=figure_width,
    )

    manifest = Manifest(
        figure_type=FigureType.STUDY_DESIGN,  # closest existing type; GA is a study overview
        caption_seed=ga.caption_seed or ga.title,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        assets=assets,
        standards=report,
        credits=_write_credits(out_dir, assets),
        warnings=warnings + raster_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest
