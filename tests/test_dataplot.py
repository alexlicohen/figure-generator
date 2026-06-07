"""M8: data_plot — dynamite ban, geom selection, SuperPlot, compliant SVG."""

from __future__ import annotations

import json

import pytest
from lxml import etree

from scidraw_agent.compose import compose_data_plot
from scidraw_agent.config import Config
from scidraw_agent.generators.data_plot import (
    DynamitePlotError,
    build_distribution_svg,
    point_alpha,
    select_geom,
)
from scidraw_agent.models import PlotRequest
from scidraw_agent.palette import PaletteRegistry
from scidraw_agent.theme import StyleSpec

SVG = "http://www.w3.org/2000/svg"


def test_geom_selection_by_sample_size():
    assert select_geom(8) == "dots"
    assert select_geom(30) == "box_points"
    assert select_geom(200) == "violin_box"


def test_point_alpha_scales_down_with_n():
    assert point_alpha(10) == 0.9
    assert point_alpha(100000) == 0.3
    assert point_alpha(10) > point_alpha(5000)


def _req(**kw):
    base = {"groups": {"control": [1.0, 2, 3, 2, 1, 2.5], "treated": [3.0, 4, 5, 4, 3, 4.5]}}
    base.update(kw)
    return PlotRequest(**base)


def test_build_is_text_as_text_and_records_geom():
    svg, actions = build_distribution_svg(_req(ylabel="signal"), StyleSpec(), PaletteRegistry())
    root = etree.fromstring(svg.encode())
    assert root.findall(f".//{{{SVG}}}text")  # text kept as text (svg.fonttype=none)
    assert any(a.rule_id == "distribution_geom" for a in actions)
    assert any(a.rule_id == "overplot_alpha" for a in actions)


def test_dynamite_blocked_without_override():
    with pytest.raises(DynamitePlotError):
        build_distribution_svg(_req(force_kind="bar"), StyleSpec(), PaletteRegistry())


def test_dynamite_allowed_with_override_is_logged():
    style = StyleSpec(allow_overrides=["no_dynamite"])
    svg, actions = build_distribution_svg(_req(force_kind="bar"), style, PaletteRegistry())
    assert svg
    assert any(a.rule_id == "no_dynamite" and not a.auto_fixed for a in actions)


def test_superplot_when_replicates_present():
    req = PlotRequest(
        groups={"treated": [1.0, 2, 3, 4, 5, 6, 7, 8, 9]},
        replicates={"treated": ["r1", "r1", "r1", "r2", "r2", "r2", "r3", "r3", "r3"]},
        ylabel="response",
    )
    _, actions = build_distribution_svg(req, StyleSpec(), PaletteRegistry())
    assert any(a.rule_id == "superplot" for a in actions)


def test_compose_data_plot_writes_outputs(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    compose_data_plot(_req(title="Signal by group"), tmp_path / "out", config=cfg)
    assert (tmp_path / "out" / "figure.svg").exists()
    assert (tmp_path / "out" / "figure.png").exists()
    data = json.loads((tmp_path / "out" / "figure.manifest.json").read_text())
    assert data["figure_type"] == "data_plot"
    assert any(a["rule_id"] == "distribution_geom" for a in data["standards"]["applied_fixes"])
