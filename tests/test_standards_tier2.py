"""Tier-2 standards rules (PLAN §5b): 3D, hatch, ticks, bubble area, contrast, abbreviations."""

from __future__ import annotations

import pytest

from scidraw_agent.standards import StyleGuardBlocked, enforce
from scidraw_agent.theme import StyleSpec

SVG = "http://www.w3.org/2000/svg"


def _wrap(body: str, w: int = 200, h: int = 200) -> str:
    return f'<svg xmlns="{SVG}" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>'


# -- no_3d [BLOCK] ----------------------------------------------------------- #
def test_3d_axes_blocks():
    svg = _wrap('<g class="axes3d"><rect x="1" y="1" width="5" height="5" fill="#000"/></g>')
    with pytest.raises(StyleGuardBlocked) as ei:
        enforce(svg)
    assert any(a.rule_id == "no_3d" for a in ei.value.actions)


def test_3d_skew_transform_blocks():
    svg = _wrap('<rect x="1" y="1" width="5" height="5" fill="#000" transform="skewX(20)"/>')
    with pytest.raises(StyleGuardBlocked):
        enforce(svg)


def test_3d_override_is_logged_not_blocked():
    svg = _wrap('<g class="axes3d"><rect x="1" y="1" width="5" height="5" fill="#000"/></g>')
    out, report = enforce(svg, StyleSpec(allow_overrides=["no_3d"]))
    assert out
    assert any(a.rule_id == "no_3d" for a in report.overrides)


# -- no_hatch [DEFAULT] ------------------------------------------------------ #
def test_hatch_pattern_replaced_with_solid():
    svg = _wrap(
        '<defs><pattern id="hx" width="4" height="4">'
        '<path d="M0 0 L4 4" stroke="#D55E00"/></pattern></defs>'
        '<rect x="10" y="10" width="50" height="50" fill="url(#hx)"/>'
    )
    out, report = enforce(svg)
    assert "url(#hx)" not in out
    assert "#D55E00" in out  # the pattern's own colour became the solid fill
    assert "<pattern" not in out  # def removed
    assert any(a.rule_id == "no_hatch" for a in report.applied_fixes)


# -- tick_density [WARN] ----------------------------------------------------- #
def test_tick_density_warns_when_busy():
    ticks = "".join(f'<g id="xtick_{i}"><line/></g>' for i in range(1, 16))
    out, report = enforce(_wrap(ticks))
    assert any(a.rule_id == "tick_density" for a in report.warnings)


def test_tick_density_quiet_when_sparse():
    ticks = "".join(f'<g id="xtick_{i}"><line/></g>' for i in range(1, 6))
    out, report = enforce(_wrap(ticks))
    assert not any(a.rule_id == "tick_density" for a in report.warnings)


# -- bubble_area [WARN] ------------------------------------------------------ #
def test_bubble_area_warns_on_many_radii():
    circles = "".join(f'<circle cx="{i*10}" cy="20" r="{i*2}" fill="#000"/>' for i in range(1, 7))
    out, report = enforce(_wrap(circles))
    assert any(a.rule_id == "bubble_area" for a in report.warnings)


def test_bubble_area_quiet_for_constant_radius():
    circles = "".join(f'<circle cx="{i*10}" cy="20" r="3" fill="#000"/>' for i in range(1, 7))
    out, report = enforce(_wrap(circles))
    assert not any(a.rule_id == "bubble_area" for a in report.warnings)


# -- text_contrast [WARN] ---------------------------------------------------- #
def test_low_contrast_text_warns():
    svg = _wrap('<text x="10" y="20" font-size="12" fill="#cccccc">faint</text>')
    out, report = enforce(svg)
    assert any(a.rule_id == "text_contrast" for a in report.warnings)


def test_dark_text_passes_contrast():
    svg = _wrap('<text x="10" y="20" font-size="12" fill="#222222">ok</text>')
    out, report = enforce(svg)
    assert not any(a.rule_id == "text_contrast" for a in report.warnings)


# -- abbreviation_legend [WARN] ---------------------------------------------- #
def test_abbreviations_warn_when_dense():
    svg = _wrap(
        '<text x="1" y="10" font-size="12">ADHD</text>'
        '<text x="1" y="30" font-size="12">DAT vs ASD</text>'
    )
    out, report = enforce(svg)
    warn = [a for a in report.warnings if a.rule_id == "abbreviation_legend"]
    assert warn and "ADHD" in warn[0].message and "DAT" in warn[0].message


def test_common_tokens_do_not_trigger_abbreviations():
    svg = _wrap('<text x="1" y="10" font-size="12">L R MRI</text>')  # all whitelisted
    out, report = enforce(svg)
    assert not any(a.rule_id == "abbreviation_legend" for a in report.warnings)
