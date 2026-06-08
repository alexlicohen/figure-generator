"""M1: style_guard post-render enforcement (DEFAULT fixes, BLOCK auto-fix/abort, overrides)."""

from __future__ import annotations

import pytest
from lxml import etree

from scidraw_agent.palette import OKABE_ITO
from scidraw_agent.standards import StyleGuardBlocked, enforce
from scidraw_agent.theme import StyleSpec

SVG = "http://www.w3.org/2000/svg"


def _wrap(body: str, w: int = 100, h: int = 100) -> str:
    return f'<svg xmlns="{SVG}" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg>'


def _parse(svg: str) -> etree._Element:
    return etree.fromstring(svg.encode())


def _findall(root, tag: str):
    return root.findall(f".//{{{SVG}}}{tag}")


def test_strips_drop_shadows():
    svg = _wrap(
        '<defs><filter id="ds"><feDropShadow dx="2" dy="2"/></filter></defs>'
        '<rect x="10" y="10" width="20" height="10" fill="#0072B2" filter="url(#ds)"/>'
    )
    out, report = enforce(svg)
    root = _parse(out)
    assert _findall(root, "filter") == []
    assert _findall(root, "rect")[0].get("filter") is None
    assert any(a.rule_id == "no_shadows" for a in report.applied_fixes)


def test_removes_graphviz_white_background_polygon():
    svg = _wrap(
        '<g class="graph"><polygon fill="white" stroke="none" '
        'points="-4,-4 -4,104 104,104 104,-4 -4,-4"/>'
        '<rect x="10" y="10" width="20" height="10" fill="#0072B2"/></g>'
    )
    out, report = enforce(svg)
    root = _parse(out)
    assert _findall(root, "polygon") == []
    assert len(_findall(root, "rect")) == 1  # the node box survives
    assert any(a.rule_id == "no_frame" for a in report.applied_fixes)


def test_removes_full_canvas_frame_rect_but_keeps_node():
    svg = _wrap(
        '<rect x="0" y="0" width="100" height="100" fill="none" stroke="black"/>'
        '<rect x="10" y="10" width="20" height="10" fill="#009E73"/>'
    )
    out, _ = enforce(svg)
    rects = _findall(_parse(out), "rect")
    assert len(rects) == 1
    assert rects[0].get("width") == "20"


def test_snaps_raw_primary_rgb():
    svg = _wrap('<rect x="1" y="1" width="20" height="10" fill="#FF0000"/>')
    out, report = enforce(svg)
    fill = _findall(_parse(out), "rect")[0].get("fill")
    assert fill in OKABE_ITO.values()
    assert fill.lower() != "#ff0000"
    assert any(a.rule_id == "no_raw_rgb" for a in report.applied_fixes)


def test_flags_red_green_pair():
    svg = _wrap(
        '<rect x="1" y="1" width="10" height="10" fill="red"/>'
        '<rect x="20" y="1" width="10" height="10" fill="green"/>'
    )
    _, report = enforce(svg)
    assert any(a.rule_id == "no_red_green" for a in report.applied_fixes)


def test_replaces_jet_gradient_with_crameri():
    stops = "".join(
        f'<stop offset="{o}" stop-color="{c}"/>'
        for o, c in [
            (0, "#0000ff"),
            (0.25, "#00ffff"),
            (0.5, "#00ff00"),
            (0.75, "#ffff00"),
            (1, "#ff0000"),
        ]
    )
    svg = _wrap(
        f'<defs><linearGradient id="jet">{stops}</linearGradient></defs>'
        '<rect x="1" y="1" width="40" height="6" fill="url(#jet)"/>'
    )
    out, report = enforce(svg)
    new_stops = [s.get("stop-color") for s in _findall(_parse(out), "stop")]
    assert "#0000ff" not in [c.lower() for c in new_stops]
    assert any(a.rule_id == "no_jet" for a in report.applied_fixes)


def test_clamps_hairline_strokes():
    svg = _wrap('<line x1="0" y1="0" x2="50" y2="0" stroke="#000000" stroke-width="0.05"/>')
    out, report = enforce(svg)
    sw = float(_findall(_parse(out), "line")[0].get("stroke-width"))
    assert sw >= StyleSpec().min_stroke_px
    assert any(a.rule_id == "min_stroke" for a in report.applied_fixes)


def _pie_wedges() -> str:
    return "".join(
        f'<path d="M50,50 L90,50 A40,40 0 0 1 {x},{y} Z" fill="#0072B2"/>'
        for x, y in [(70, 86), (20, 70), (40, 18)]
    )


def test_pie_auto_converts_to_sorted_bar():
    # A7: pie/donut -> auto-convert to a sorted horizontal bar (position/length encoding).
    out, report = enforce(_wrap(_pie_wedges()))
    root = _parse(out)
    arcs = [p for p in _findall(root, "path") if "A" in (p.get("d") or "")]
    assert not arcs  # wedge arcs replaced
    assert _findall(root, "rect")  # bars drawn
    assert any(a.rule_id == "no_pie" and a.auto_fixed for a in report.applied_fixes)


def test_pie_override_keeps_pie():
    out, report = enforce(_wrap(_pie_wedges()), StyleSpec(allow_overrides=["no_pie"]))
    root = _parse(out)
    arcs = [p for p in _findall(root, "path") if "A" in (p.get("d") or "")]
    assert arcs  # wedges kept untouched
    assert any(a.rule_id == "no_pie" for a in report.overrides)


def test_pie_unrecoverable_values_refuses():
    # Detected as a pie (explicit hint) but no parseable arc geometry -> cannot recover
    # slice values, so refuse rather than fabricate a bar.
    svg = _wrap('<g class="pie"><rect x="10" y="10" width="20" height="20" fill="#0072B2"/></g>')
    with pytest.raises(StyleGuardBlocked) as exc:
        enforce(svg)
    assert any(a.rule_id == "no_pie" for a in exc.value.actions)


def test_sub_minimum_font_aborts():
    with pytest.raises(StyleGuardBlocked) as exc:
        enforce(_wrap('<text x="5" y="5" font-size="3">tiny</text>'))
    assert any(a.rule_id == "min_font" for a in exc.value.actions)


def test_font_override_clamps_instead_of_aborting():
    out, report = enforce(
        _wrap('<text x="5" y="5" font-size="3">tiny</text>'),
        StyleSpec(allow_overrides=["min_font"]),
    )
    size = float(_findall(_parse(out), "text")[0].get("font-size"))
    assert size >= StyleSpec().min_font_px
    assert any(a.rule_id == "min_font" for a in report.applied_fixes)


def test_ugly_svg_comes_out_compliant_and_text_preserved():
    svg = _wrap(
        '<defs><filter id="s"><feDropShadow dx="1" dy="1"/></filter></defs>'
        '<rect x="0" y="0" width="100" height="100" fill="white"/>'
        '<rect x="10" y="10" width="30" height="12" fill="#FF0000" filter="url(#s)"/>'
        '<text x="12" y="20" font-size="8" font-family="Arial">M1</text>'
        '<line x1="40" y1="16" x2="80" y2="16" stroke="#000000" stroke-width="0.05"/>'
    )
    out, report = enforce(svg)
    root = _parse(out)
    assert _findall(root, "filter") == []  # no shadows
    assert len(_findall(root, "rect")) == 1  # background frame gone, node kept
    assert _findall(root, "rect")[0].get("fill") in OKABE_ITO.values()  # RGB snapped
    assert _findall(root, "text")[0].text == "M1"  # text kept as text
    assert float(_findall(root, "line")[0].get("stroke-width")) >= StyleSpec().min_stroke_px
    assert report.applied_fixes  # something was enforced
