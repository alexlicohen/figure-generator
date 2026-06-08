"""Figure export: vector (SVG/PDF/EPS) + raster (PNG/TIFF) at journal physical size & DPI.

SVG is the primary, editable deliverable (see the brief); everything here is secondary and
best-effort, so a missing libcairo / Pillow never fails a run — the SVG still ships and the
gap is recorded as a warning. The same guarded SVG feeds every format, so all carry the same
stroke/font floors. Physical sizing (``figure_width``) sets the SVG's mm width before render,
so the PDF/EPS come out at column width and the raster lands at exactly DPI×physical-size.
CMYK is a naive, non-colour-managed conversion (honest warning attached) — true CMYK wants the
journal's ICC profile.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .theme import StyleSpec

SVG_NS = "http://www.w3.org/2000/svg"
MM_PER_IN = 25.4


def _ensure_cairo_discoverable() -> None:
    """On macOS, point cffi's dlopen at Homebrew's libcairo if it isn't already findable.

    cairocffi (under cairosvg) dlopen()s ``libcairo.2.dylib`` by leaf name, and the dynamic
    loader does not search Homebrew's lib dir by default — so an installed cairo is invisible.
    Setting ``DYLD_FALLBACK_LIBRARY_PATH`` before the import is honoured by dlopen. No-op when
    already set, on non-macOS, or when no Homebrew cairo is present.
    """
    import os
    import sys

    if sys.platform != "darwin" or "DYLD_FALLBACK_LIBRARY_PATH" in os.environ:
        return
    for base in ("/opt/homebrew", "/usr/local"):
        libdir = f"{base}/lib"
        if Path(libdir, "libcairo.2.dylib").exists():
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = libdir
            return


def _viewbox_aspect(root: etree._Element) -> float:
    """width/height aspect ratio from viewBox (or width/height attrs); defaults to 1.0."""
    import re

    def num(v):
        m = re.match(r"[\d.]+", v or "")
        return float(m.group()) if m else 0.0

    vb = root.get("viewBox")
    if vb:
        p = vb.replace(",", " ").split()
        if len(p) == 4 and float(p[3]):
            return float(p[2]) / float(p[3])
    w, h = num(root.get("width")), num(root.get("height"))
    return (w / h) if (w and h) else 1.0


def resize_svg_to_mm(svg: str, width_mm: float, max_height_mm: float) -> str:
    """Set the SVG's physical width/height in mm (preserving the viewBox aspect).

    Caps the height at ``max_height_mm`` (journals reject over-tall figures), shrinking the
    width to keep the aspect. Leaves the viewBox untouched so coordinates are unchanged.
    """
    root = etree.fromstring(svg.encode())
    aspect = _viewbox_aspect(root) or 1.0
    w_mm = width_mm
    h_mm = w_mm / aspect
    if max_height_mm and h_mm > max_height_mm:
        h_mm = max_height_mm
        w_mm = h_mm * aspect
    # Guarantee a viewBox so the mm box maps back to the original user coordinates.
    if not root.get("viewBox"):
        import re

        def num(v):
            m = re.match(r"[\d.]+", v or "")
            return float(m.group()) if m else 0.0

        w, h = num(root.get("width")) or 100, num(root.get("height")) or 100
        root.set("viewBox", f"0 0 {w:g} {h:g}")
    root.set("width", f"{w_mm:g}mm")
    root.set("height", f"{h_mm:g}mm")
    return etree.tostring(root, xml_declaration=True, encoding="utf-8").decode()


# Column keyword -> attribute on the journal preset giving the physical width in mm.
_WIDTH_ATTR = {"single": "single_col_mm", "double": "double_col_mm"}


def export_artifacts(
    svg: str,
    out_dir: str | Path,
    style: StyleSpec,
    *,
    formats: list[str],
    figure_width: str = "none",
) -> tuple[list[str], list[str]]:
    """Write the requested formats; return (paths, warnings).

    ``formats`` ⊆ {svg, png, pdf, eps, tiff}. ``figure_width`` ∈ {none, single, double} sizes
    the figure to the journal column width in mm before rendering (vector physical size +
    raster px = DPI×size). TIFF is written CMYK when the journal preset is CMYK (Science),
    else RGB. PNG/TIFF get a white background (the guard strips the generator's frame).
    """
    out_dir = Path(out_dir)
    wanted = [f.lower() for f in formats]
    paths: list[str] = []
    warnings: list[str] = []
    if not wanted:
        return paths, warnings

    preset = style.preset
    dpi = preset.raster_dpi
    sized = svg
    if figure_width in _WIDTH_ATTR:
        width_mm = getattr(preset, _WIDTH_ATTR[figure_width])
        sized = resize_svg_to_mm(svg, width_mm, preset.max_height_mm)

    # A plain sized SVG copy is cheap and never needs cairo.
    if "svg" in wanted:
        p = out_dir / "figure.export.svg"
        p.write_text(sized)
        paths.append(str(p))

    needs_cairo = any(f in wanted for f in ("png", "pdf", "eps", "tiff"))
    if not needs_cairo:
        return paths, warnings

    _ensure_cairo_discoverable()
    try:
        import cairosvg
    except Exception as exc:  # ImportError, or OSError when libcairo can't be dlopen'd
        warnings.append(
            f"raster/vector export skipped: cairosvg/libcairo unavailable ({type(exc).__name__}). "
            "SVG written; install cairo (e.g. `brew install cairo`) for PNG/PDF/EPS/TIFF."
        )
        return paths, warnings

    data = sized.encode()
    if "png" in wanted:
        p = out_dir / "figure.png"
        cairosvg.svg2png(bytestring=data, write_to=str(p), dpi=dpi, background_color="white")
        paths.append(str(p))
    if "pdf" in wanted:
        p = out_dir / "figure.pdf"
        cairosvg.svg2pdf(bytestring=data, write_to=str(p))
        paths.append(str(p))
    if "eps" in wanted:
        p = out_dir / "figure.eps"
        cairosvg.svg2eps(bytestring=data, write_to=str(p))
        paths.append(str(p))
        if preset.colorspace == "CMYK":
            warnings.append(
                "EPS is RGB vector (cairo has no CMYK vector path); for a CMYK vector send the "
                "PDF/EPS through the journal's ICC profile in Acrobat/Ghostscript at revision."
            )
    if "tiff" in wanted:
        tpaths, twarn = _export_tiff(cairosvg, data, out_dir, dpi, preset.colorspace)
        paths += tpaths
        warnings += twarn
    return paths, warnings


def _export_tiff(cairosvg, data, out_dir, dpi, colorspace) -> tuple[list[str], list[str]]:
    """PNG→Pillow→TIFF (LZW), in CMYK when the journal wants it (with an honesty warning)."""
    try:
        import io

        from PIL import Image
    except Exception as exc:
        return [], [f"TIFF export skipped: Pillow unavailable ({type(exc).__name__})."]
    png = cairosvg.svg2png(bytestring=data, dpi=dpi, background_color="white")
    im = Image.open(io.BytesIO(png)).convert("RGB")
    warnings: list[str] = []
    if colorspace == "CMYK":
        im = im.convert("CMYK")  # naive, non-colour-managed
        warnings.append(
            "TIFF written in CMYK via a naive conversion (no ICC profile). For an accurate "
            "proof, reconvert from the RGB master using the journal's CMYK ICC profile."
        )
    p = out_dir / "figure.tiff"
    im.save(str(p), format="TIFF", dpi=(dpi, dpi), compression="tiff_lzw")
    return [str(p)], warnings
