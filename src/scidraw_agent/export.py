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
    cmyk_profile: str | None = None,
) -> tuple[list[str], list[str]]:
    """Write the requested formats; return (paths, warnings).

    ``formats`` ⊆ {svg, png, pdf, eps, tiff}. ``figure_width`` ∈ {none, single, double} sizes
    the figure to the journal column width in mm before rendering (vector physical size +
    raster px = DPI×size). TIFF is written CMYK when the journal preset is CMYK (Science),
    else RGB. ``cmyk_profile`` (or ``$SCIDRAW_CMYK_ICC``) is a CMYK ICC profile path for a
    colour-managed conversion; without it the conversion is naive (flagged). PNG/TIFF get a
    white background (the guard strips the generator's frame).
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
        tpaths, twarn = _export_tiff(cairosvg, data, out_dir, dpi, preset.colorspace, cmyk_profile)
        paths += tpaths
        warnings += twarn
    return paths, warnings


def _export_tiff(
    cairosvg, data, out_dir, dpi, colorspace, cmyk_profile
) -> tuple[list[str], list[str]]:
    """PNG→Pillow→TIFF (LZW). For CMYK journals, prefer an ICC-managed conversion when a
    profile is available (``cmyk_profile`` or ``$SCIDRAW_CMYK_ICC``), else a naive convert."""
    import os

    try:
        import io

        from PIL import Image
    except Exception as exc:
        return [], [f"TIFF export skipped: Pillow unavailable ({type(exc).__name__})."]
    png = cairosvg.svg2png(bytestring=data, dpi=dpi, background_color="white")
    im = Image.open(io.BytesIO(png)).convert("RGB")
    warnings: list[str] = []
    save_kwargs: dict = {}
    if colorspace == "CMYK":
        profile = cmyk_profile or os.environ.get("SCIDRAW_CMYK_ICC")
        im, icc_bytes, warnings = _to_cmyk(im, profile)
        if icc_bytes:
            save_kwargs["icc_profile"] = icc_bytes  # embed so the TIFF is colour-managed
    p = out_dir / "figure.tiff"
    im.save(str(p), format="TIFF", dpi=(dpi, dpi), compression="tiff_lzw", **save_kwargs)
    return [str(p)], warnings


def _to_cmyk(im, profile: str | None):
    """Convert an RGB image to CMYK. Returns (image, embedded_icc_bytes_or_None, warnings).

    With a valid CMYK ICC profile → ImageCms sRGB→CMYK transform (relative colorimetric) and the
    profile embedded. Without one (or if it can't be loaded) → naive ``convert('CMYK')`` with an
    honest warning that it isn't colour-managed.
    """
    if profile and Path(profile).exists():
        try:
            from PIL import ImageCms

            src = ImageCms.createProfile("sRGB")
            dst = ImageCms.getOpenProfile(profile)
            transform = ImageCms.buildTransform(
                src, dst, "RGB", "CMYK",
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            )
            out = ImageCms.applyTransform(im, transform)
            return out, dst.tobytes(), [
                f"TIFF written in CMYK via ICC profile '{Path(profile).name}' "
                "(relative colorimetric, embedded)."
            ]
        except Exception as exc:  # malformed profile / cms failure — fall back honestly
            return im.convert("CMYK"), None, [
                f"CMYK ICC transform failed ({type(exc).__name__}); used a naive conversion. "
                f"Check the profile at {profile}."
            ]
    msg = (
        "TIFF written in CMYK via a naive conversion (no ICC profile). Set $SCIDRAW_CMYK_ICC to "
        "the journal's CMYK ICC profile for a colour-managed proof."
    )
    if profile:  # a path was given but doesn't exist
        msg = f"CMYK ICC profile not found at {profile}; used a naive conversion. " + msg
    return im.convert("CMYK"), None, [msg]
