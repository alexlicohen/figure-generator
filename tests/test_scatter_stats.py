"""Scatter/correlation + significance-bracket annotations and the stats helpers."""

from __future__ import annotations

import json

from lxml import etree

from scidraw_agent.compose import compose_scatter
from scidraw_agent.config import Config
from scidraw_agent.generators.data_plot import build_distribution_svg, build_scatter_svg
from scidraw_agent.models import PlotRequest, ScatterRequest
from scidraw_agent.palette import PaletteRegistry
from scidraw_agent.stats import compare, fmt_p, linfit, p_to_stars
from scidraw_agent.theme import StyleSpec

SVG = "http://www.w3.org/2000/svg"


def _texts(svg):
    root = etree.fromstring(svg.encode())
    return [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]


# -- stats helpers ----------------------------------------------------------- #
def test_linfit_recovers_strong_positive_correlation():
    x = list(range(20))
    y = [2 * v + 1 for v in x]  # perfectly linear
    fit = linfit(x, y)
    assert round(fit.slope, 3) == 2.0
    assert fit.r > 0.999
    assert fit.p < 1e-3
    assert fit.n == 20
    assert (fit.hi >= fit.lo).all()  # band is well-formed


def test_compare_detects_separated_groups_with_effect_size():
    a = [1.0, 1.2, 0.9, 1.1, 1.0, 0.8]
    b = [3.0, 3.2, 2.9, 3.1, 3.0, 2.8]  # clearly higher
    cmp = compare(a, b)
    assert cmp.test == "Welch t"
    assert cmp.p < 0.01
    assert cmp.effect > 0.8  # large effect
    assert "Cohen" in cmp.effect_name or "Hedges" in cmp.effect_name


def test_p_to_stars_and_fmt_p():
    assert p_to_stars(0.2) == "ns"
    assert p_to_stars(0.03) == "*"
    assert p_to_stars(0.004) == "**"
    assert p_to_stars(1e-5) == "****"
    assert fmt_p(0.0001) == "p < .001"
    assert fmt_p(0.034) == "p = .034"  # no leading zero


def test_mann_whitney_path():
    cmp = compare([1, 2, 3, 4], [5, 6, 7, 8], parametric=False)
    assert cmp.test == "Mann-Whitney U"
    assert cmp.effect_name == "rank-biserial r"


# -- scatter ----------------------------------------------------------------- #
def test_scatter_draws_fit_and_reports_r_p_n():
    x = [i + (i % 3) * 0.1 for i in range(30)]
    y = [0.8 * v + 2 + (v % 2) for v in x]
    svg, actions = build_scatter_svg(
        ScatterRequest(x=x, y=y, xlabel="dose", ylabel="response"),
        StyleSpec(),
        PaletteRegistry(),
    )
    assert any(a.rule_id == "stat_reporting" for a in actions)
    texts = _texts(svg)
    assert any("r =" in t and "n =" in t for t in texts)  # annotation embedded as text


def test_scatter_colours_by_group_and_legends():
    svg, actions = build_scatter_svg(
        ScatterRequest(
            x=[1, 2, 3, 4, 5, 6],
            y=[1, 2, 1, 5, 6, 5],
            groups=["NT", "NT", "NT", "ASD", "ASD", "ASD"],
        ),
        StyleSpec(),
        PaletteRegistry(),
    )
    assert {"NT", "ASD"} <= set(_texts(svg))  # legend labels present
    # groups carry a redundant marker shape (colour-blind safe), recorded for the manifest
    assert any(a.rule_id == "group_shape" for a in actions)


def test_compose_scatter_writes_outputs(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    m = compose_scatter(
        ScatterRequest(x=list(range(15)), y=[2 * i for i in range(15)], title="corr"),
        tmp_path / "out",
        config=cfg,
    )
    assert (tmp_path / "out" / "figure.svg").exists()
    data = json.loads((tmp_path / "out" / "figure.manifest.json").read_text())
    assert any(
        a["rule_id"] == "stat_reporting" for a in data["standards"]["applied_fixes"]
    )
    assert m.figure_type == "data_plot"


# -- significance brackets on distributions ---------------------------------- #
def test_distribution_sig_brackets_record_exact_stats():
    req = PlotRequest(
        groups={
            "control": [1.0, 1.2, 0.9, 1.1, 1.0, 0.8, 1.05],
            "ADHD": [3.0, 3.2, 2.9, 3.1, 3.0, 2.8, 3.05],
        },
        annotate_stats=True,
        ylabel="score",
    )
    svg, actions = build_distribution_svg(req, StyleSpec(), PaletteRegistry())
    stat_actions = [a for a in actions if a.rule_id == "stat_reporting"]
    assert stat_actions
    assert "control vs ADHD" in stat_actions[0].message
    texts = _texts(svg)
    assert any(t in ("*", "**", "***", "****") for t in texts)  # a star bracket was drawn
    assert any("n=" in (t or "") for t in texts)  # n appended to tick labels


def test_distribution_explicit_comparisons():
    req = PlotRequest(
        groups={"a": [1.0, 2, 1], "b": [2.0, 3, 2], "c": [5.0, 6, 5]},
        annotate_stats=True,
        comparisons=[["a", "c"]],
    )
    _, actions = build_distribution_svg(req, StyleSpec(), PaletteRegistry())
    msgs = [a.message for a in actions if a.rule_id == "stat_reporting"]
    assert len(msgs) == 1 and "a vs c" in msgs[0]
