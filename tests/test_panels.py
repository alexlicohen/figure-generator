"""Multi-panel composition: schematic grid + shared legend, and shared-axis data-plot panels."""

from __future__ import annotations

import json

from lxml import etree

from scidraw_agent.compose import compose_panels, compose_plot_panels
from scidraw_agent.config import Config
from scidraw_agent.generators.data_plot import build_distribution_panels_svg
from scidraw_agent.models import Entity, FigureSchema, FigureType, PlotRequest
from scidraw_agent.palette import PaletteRegistry
from scidraw_agent.theme import StyleSpec, cohen_lab

SVG = "http://www.w3.org/2000/svg"


def _texts(svg: str):
    root = etree.fromstring(svg.encode())
    return [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]


def _circuit(label, group):
    return FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id=label[:2].lower(), label=label, group=group)],
    )


# -- schematic grid + shared legend ----------------------------------------- #
def test_panels_grid_layout_and_shared_legend(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    reg = PaletteRegistry()
    schemas = [
        _circuit("Patients", "patients"),
        _circuit("Controls", "control"),
        _circuit("Siblings", "siblings"),
        _circuit("All", "patients"),
    ]
    manifest = compose_panels(
        schemas, tmp_path / "out", config=cfg, palette=reg, ncols=2, fetcher=None
    )
    svg = (tmp_path / "out" / "figure.svg").read_text()
    root = etree.fromstring(svg.encode())
    # 2x2 grid is taller than wide-ish; A/B/C/D letters present
    assert {"A", "B", "C", "D"} <= set(_texts(svg))
    # one shared legend group, listing each distinct group once
    legends = root.findall(f".//{{{SVG}}}g[@class='panel-legend']")
    assert len(legends) == 1
    legend_texts = [t.text for t in legends[0].findall(f".//{{{SVG}}}text")]
    assert set(legend_texts) == {"patients", "control", "siblings"}
    assert manifest.svg_path


def test_panels_single_group_has_no_legend(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    manifest = compose_panels(
        [_circuit("Patients", "patients"), _circuit("More", "patients")],
        tmp_path / "out", config=cfg, fetcher=None,
    )
    svg = (tmp_path / "out" / "figure.svg").read_text()
    root = etree.fromstring(svg.encode())
    assert root.findall(f".//{{{SVG}}}g[@class='panel-legend']") == []  # 1 group -> no legend
    assert manifest.svg_path


# -- shared-axis data-plot panels -------------------------------------------- #
def test_plot_panels_share_axis_and_legend():
    reqs = [
        PlotRequest(
            groups={"NT": [1.0, 2, 1, 2], "ASD": [3.0, 4, 3, 4]}, ylabel="DAT", title="ROI 1"
        ),
        PlotRequest(groups={"NT": [2.0, 3, 2], "ASD": [4.0, 5, 4]}, title="ROI 2"),
    ]
    reg = PaletteRegistry()
    svg, actions = build_distribution_panels_svg(reqs, cohen_lab(), reg)
    texts = _texts(svg)
    assert {"A", "B"} <= set(texts)  # panel letters
    assert "ROI 1" in texts and "ROI 2" in texts
    # NT and ASD keep one stable colour across panels (shared registry)
    assert "NT" in reg.mapping and "ASD" in reg.mapping
    # geom action recorded once (deduped across panels)
    assert sum(a.rule_id == "distribution_geom" for a in actions) == 1


def test_compose_plot_panels_writes_outputs(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    reqs = [
        PlotRequest(groups={"a": [1.0, 2, 3], "b": [2.0, 3, 4]}, ylabel="y"),
        PlotRequest(groups={"a": [1.5, 2.5], "b": [3.0, 3.5]}),
    ]
    compose_plot_panels(reqs, tmp_path / "out", config=cfg, style=StyleSpec())
    assert (tmp_path / "out" / "figure.svg").exists()
    data = json.loads((tmp_path / "out" / "figure.manifest.json").read_text())
    assert data["figure_type"] == "data_plot"
