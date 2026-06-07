"""Assemble generator output into a compliant figure + manifest.

Every generator's SVG is run through `style_guard.enforce` before anything is written, so
the figure on disk is guaranteed compliant. Raster export (cairosvg) inherits the guarded
SVG, so PNG/PDF carry the same stroke/font floors. The manifest records license provenance
(per asset) and standards provenance (applied fixes / overrides / warnings).
"""

from __future__ import annotations

from pathlib import Path

import cairosvg
from lxml import etree

from .config import Config, load_config
from .models import FigureSchema, Manifest
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


def _export_raster(svg: str, out_dir: Path, dpi: int, *, png: bool, pdf: bool) -> list[str]:
    paths: list[str] = []
    data = svg.encode()
    if png:
        p = out_dir / "figure.png"
        cairosvg.svg2png(bytestring=data, write_to=str(p), dpi=dpi)
        paths.append(str(p))
    if pdf:
        p = out_dir / "figure.pdf"
        cairosvg.svg2pdf(bytestring=data, write_to=str(p))
        paths.append(str(p))
    return paths


def compose_figure(
    schema: FigureSchema,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    style: StyleSpec | None = None,
    fetcher=None,
    palette: PaletteRegistry | None = None,
    export_png: bool = True,
    export_pdf: bool = False,
) -> Manifest:
    """Generate, enforce standards, export, and write figure.svg + figure.manifest.json."""
    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = route(schema.figure_type).generate(schema, style, palette, fetcher=fetcher)
    cleaned, report = enforce(result.svg, style, data_kind=schema.data_kind)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(cleaned)
    rasters = _export_raster(
        cleaned, out_dir, style.preset.raster_dpi, png=export_png, pdf=export_pdf
    )

    manifest = Manifest(
        figure_type=schema.figure_type,
        caption_seed=schema.caption_seed,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        assets=result.assets,
        standards=report,
        warnings=result.warnings,
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
    export_png: bool = True,
) -> Manifest:
    """Tile multiple figures into one multi-panel SVG with A/B/C letters.

    One shared PaletteRegistry is used across panels, so a group keeps the same colour in
    every panel (stable group->colour mapping).
    """
    from svgutils import transform as st

    config = config or load_config()
    style = style or StyleSpec(journal=config.journal)
    palette = palette or PaletteRegistry()  # shared across panels
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

    letter_gap, panel_gap, top = 22.0, 36.0, 6.0
    x_cursor = 0.0
    max_h = 0.0
    elements = []
    for i, svg in enumerate(panels):
        w, h = _viewport(svg)
        fig = st.fromstring(svg)
        root = fig.getroot()
        root.moveto(x_cursor, top + letter_gap)
        elements.append(root)
        elements.append(
            st.TextElement(
                x_cursor + 2,
                top + letter_gap - 6,
                chr(ord("A") + i),
                size=16,
                weight="bold",
                font="Arial",
            )
        )
        x_cursor += w + panel_gap
        max_h = max(max_h, h)

    total_w = max(1.0, x_cursor - panel_gap)
    total_h = top + letter_gap + max_h + 6
    base = st.SVGFigure(f"{total_w}px", f"{total_h}px")
    base.append(elements)
    combined = base.to_str().decode()

    # ensure width/height/viewBox for raster + final guard, then enforce once more
    root = etree.fromstring(combined.encode())
    root.set("width", f"{total_w:g}")
    root.set("height", f"{total_h:g}")
    root.set("viewBox", f"0 0 {total_w:g} {total_h:g}")
    combined, report_final = enforce(etree.tostring(root).decode(), style)
    if report_total is not None:
        report_total.applied_fixes.extend(report_final.applied_fixes)

    svg_path = out_dir / "figure.svg"
    svg_path.write_text(combined)
    rasters = _export_raster(combined, out_dir, style.preset.raster_dpi, png=export_png, pdf=False)

    manifest = Manifest(
        figure_type=schemas[0].figure_type,
        svg_path=str(svg_path),
        raster_paths=rasters,
        journal=style.journal,
        assets=all_assets,
        standards=report_total or enforce("<svg/>", style)[1],
        warnings=all_warnings,
    )
    (out_dir / "figure.manifest.json").write_text(manifest.model_dump_json(indent=2))
    return manifest
