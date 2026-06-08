"""Export completeness: mm sizing, multi-format raster/vector, CMYK TIFF, graceful fallback."""

from __future__ import annotations

import json

from lxml import etree

from scidraw_agent.compose import compose_scatter
from scidraw_agent.config import Config
from scidraw_agent.export import export_artifacts, resize_svg_to_mm
from scidraw_agent.models import ScatterRequest
from scidraw_agent.theme import StyleSpec

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">'
    '<rect x="10" y="10" width="80" height="40" fill="#2F5C8A"/></svg>'
)


def test_resize_to_mm_sets_physical_size_keeps_viewbox():
    out = resize_svg_to_mm(SVG, width_mm=89, max_height_mm=170)
    root = etree.fromstring(out.encode())
    assert root.get("width") == "89mm"
    # aspect 200:100 -> height 44.5 mm
    assert root.get("height") == "44.5mm"
    assert root.get("viewBox") == "0 0 200 100"  # coordinates untouched


def test_resize_caps_overtall_height():
    tall = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 1000"><rect/></svg>'
    out = resize_svg_to_mm(tall, width_mm=89, max_height_mm=170)
    root = etree.fromstring(out.encode())
    # height would be 890 mm; capped to 170, width shrinks to keep aspect (17 mm)
    assert root.get("height") == "170mm"
    assert root.get("width") == "17mm"


def test_export_writes_requested_raster_and_vector(tmp_path):
    style = StyleSpec(journal="nature")
    paths, warnings = export_artifacts(
        SVG, tmp_path, style, formats=["png", "pdf", "eps"], figure_width="single"
    )
    names = {p.rsplit("/", 1)[-1] for p in paths}
    # cairo is available locally; if not, this degrades to a warning (asserted below)
    if warnings and any("cairosvg" in w for w in warnings):
        assert names == set()
    else:
        assert {"figure.png", "figure.pdf", "figure.eps"} <= names


def test_cmyk_tiff_for_cmyk_journal(tmp_path):
    style = StyleSpec(journal="science")  # CMYK preset
    paths, warnings = export_artifacts(SVG, tmp_path, style, formats=["tiff"])
    if any("cairosvg" in w or "Pillow" in w for w in warnings):
        return  # environment without cairo/Pillow — fallback path, nothing to assert
    assert any(p.endswith("figure.tiff") for p in paths)
    assert any("CMYK" in w for w in warnings)  # honesty about the naive conversion
    from PIL import Image

    tiff = next(p for p in paths if p.endswith(".tiff"))
    assert Image.open(tiff).mode == "CMYK"


def test_no_formats_writes_nothing(tmp_path):
    paths, warnings = export_artifacts(SVG, tmp_path, StyleSpec(), formats=[])
    assert paths == [] and warnings == []


def test_compose_scatter_multiformat_records_rasters(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    m = compose_scatter(
        ScatterRequest(x=list(range(12)), y=[2 * i for i in range(12)]),
        tmp_path / "out",
        config=cfg,
        export_pdf=True,
        export_eps=True,
        figure_width="double",
    )
    data = json.loads((tmp_path / "out" / "figure.manifest.json").read_text())
    rasters = {p.rsplit("/", 1)[-1] for p in data["raster_paths"]}
    if not any("cairosvg" in w for w in m.warnings):
        assert {"figure.png", "figure.pdf", "figure.eps"} <= rasters
