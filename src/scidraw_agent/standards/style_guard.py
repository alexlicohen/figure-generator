"""Post-render SVG enforcement — the silent layer.

`enforce()` runs on the output of *every* generator before the manifest is written, so a
non-compliant figure cannot be produced regardless of which generator created it. It applies
DEFAULT fixes silently, auto-converts overridable BLOCK violations, and aborts (raises
`StyleGuardBlocked`) on BLOCK violations it cannot safely auto-fix unless the rule is in the
StyleSpec escape hatch. Every action is recorded in the returned `StandardsReport`.
"""

from __future__ import annotations

import re

from lxml import etree

from .. import palette
from ..models import DataKind, StandardsAction, StandardsReport
from ..theme import PT_TO_PX, StyleSpec
from .linter import RuleId, rule

_LEADING_NUMBER = re.compile(r"^\s*(-?\d*\.?\d+)")

_WHITE = {"white", "#fff", "#ffffff", "none", ""}


class StyleGuardBlocked(Exception):
    """Raised when an un-overridden BLOCK violation cannot be safely auto-fixed."""

    def __init__(self, actions: list[StandardsAction], report: StandardsReport) -> None:
        self.actions = actions
        self.report = report
        super().__init__("; ".join(a.message for a in actions))


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _local(el: etree._Element) -> str:
    tag = el.tag
    if not isinstance(tag, str):  # comments / processing instructions
        return ""
    return tag.split("}")[-1]


def _num(s: str | None) -> float | None:
    """Leading number from a length string (handles 'px', 'pt', 'mm', '%' suffixes)."""
    if not s:
        return None
    m = _LEADING_NUMBER.match(s)
    return float(m.group(1)) if m else None


def _parse_style(value: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in (value or "").split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _serialize_style(props: dict[str, str]) -> str:
    return ";".join(f"{k}:{v}" for k, v in props.items())


def _viewport(root: etree._Element) -> tuple[float, float]:
    vb = root.get("viewBox")
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    return (_num(root.get("width")) or 0.0, _num(root.get("height")) or 0.0)


def _font_size_px(value: str | None) -> float | None:
    if not value:
        return None
    v = value.strip().lower()
    mult = 1.0
    for unit in ("px", "pt"):
        if v.endswith(unit):
            v = v[: -len(unit)]
            mult = PT_TO_PX if unit == "pt" else 1.0
            break
    try:
        return float(v) * mult
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# enforcement
# --------------------------------------------------------------------------- #
def enforce(
    svg: str | bytes,
    style: StyleSpec | None = None,
    *,
    data_kind: DataKind | None = None,
    report: StandardsReport | None = None,
) -> tuple[str, StandardsReport]:
    """Enforce design standards on an SVG string. Returns (cleaned_svg, report)."""
    style = style or StyleSpec()
    report = report or StandardsReport()
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    root = etree.fromstring(svg.encode() if isinstance(svg, str) else svg, parser=parser)
    elements = list(root.iter())
    blocked: list[StandardsAction] = []

    _strip_shadows(root, elements, style, report)
    _remove_frame(root, elements, style, report)
    _clamp_strokes(elements, style, report)
    _demote_gridlines(elements, style, report)
    _snap_colors(elements, style, report)
    _fix_rainbow_gradients(root, style, report, data_kind)
    _check_pie(root, style, report, blocked)
    _check_fonts(root, style, report, blocked)

    if blocked:
        raise StyleGuardBlocked(blocked, report)

    out = etree.tostring(root, xml_declaration=True, encoding="utf-8").decode()
    return out, report


def _action(rule_id: RuleId, *, auto_fixed: bool, message: str | None = None) -> StandardsAction:
    r = rule(rule_id)
    return StandardsAction(
        rule_id=str(rule_id),
        tier=r.tier,
        message=message or r.message,
        auto_fixed=auto_fixed,
        source_url=r.source_url,
    )


# -- DEFAULT fixes ----------------------------------------------------------- #
def _strip_shadows(root, elements, style: StyleSpec, report: StandardsReport) -> None:
    if not style.strip_shadows:
        return
    removed = 0
    for el in elements:
        if _local(el) == "filter":
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                removed += 1
    for el in root.iter():
        if el.get("filter"):
            del el.attrib["filter"]
            removed += 1
        props = _parse_style(el.get("style"))
        if "filter" in props or "box-shadow" in props:
            props.pop("filter", None)
            props.pop("box-shadow", None)
            el.set("style", _serialize_style(props))
            removed += 1
    if removed:
        report.add(_action(RuleId.NO_SHADOWS, auto_fixed=True))


def _remove_frame(root, elements, style: StyleSpec, report: StandardsReport) -> None:
    if not style.hide_top_right_spines:
        return
    w, h = _viewport(root)
    if not (w and h):
        return
    removed = 0
    for el in elements:
        name = _local(el)
        if name not in ("rect", "polygon"):
            continue
        fill = (el.get("fill") or _parse_style(el.get("style")).get("fill", "")).strip().lower()
        if name == "rect":
            rw = _num(el.get("width")) or 0.0
            rh = _num(el.get("height")) or 0.0
            covers = rw >= 0.95 * w and rh >= 0.95 * h
            if covers and (fill in _WHITE):
                el.getparent().remove(el)
                removed += 1
        else:  # graphviz emits a full-canvas white background polygon
            if fill in _WHITE and el.get("points") and len((el.get("points") or "").split()) <= 6:
                el.getparent().remove(el)
                removed += 1
    if removed:
        report.add(_action(RuleId.NO_FRAME, auto_fixed=True))


def _clamp_strokes(elements, style: StyleSpec, report: StandardsReport) -> None:
    floor = style.min_stroke_px
    fixed = 0
    for el in elements:
        sw = el.get("stroke-width")
        if sw is not None:
            try:
                if 0 < float(sw) < floor:
                    el.set("stroke-width", str(floor))
                    fixed += 1
            except ValueError:
                pass
        props = _parse_style(el.get("style"))
        if "stroke-width" in props:
            try:
                val = float(props["stroke-width"].rstrip("px"))
                if 0 < val < floor:
                    props["stroke-width"] = str(floor)
                    el.set("style", _serialize_style(props))
                    fixed += 1
            except ValueError:
                pass
    if fixed:
        report.add(
            _action(
                RuleId.MIN_STROKE, auto_fixed=True, message=f"Clamped {fixed} hairline stroke(s)."
            )
        )


def _demote_gridlines(elements, style: StyleSpec, report: StandardsReport) -> None:
    fixed = 0
    for el in elements:
        cls = (el.get("class") or "").lower()
        if "grid" in cls:
            el.set("stroke", style.gridline_color)
            el.set("stroke-width", f"{style.gridline_width_px:g}")
            fixed += 1
    if fixed:
        report.add(_action(RuleId.GRIDLINE_DEMOTE, auto_fixed=True))


# -- colour ------------------------------------------------------------------ #
def _snap_colors(elements, style: StyleSpec, report: StandardsReport) -> None:
    overridden = style.is_overridden(RuleId.NO_RAW_RGB)
    snapped = 0
    saw_red = saw_green = False
    for el in elements:
        for attr in ("fill", "stroke"):
            val = el.get(attr)
            if val and palette.is_raw_primary(val):
                rgb = palette.parse_color(val)
                if rgb:
                    hue = palette.hue_deg(rgb)
                    saw_red = saw_red or (hue < 20 or hue > 340)
                    saw_green = saw_green or (80 < hue < 160)
                if not overridden:
                    el.set(attr, palette.snap_to_palette(val))
                    snapped += 1
        props = _parse_style(el.get("style"))
        changed = False
        for prop in ("fill", "stroke"):
            val = props.get(prop)
            if val and palette.is_raw_primary(val) and not overridden:
                props[prop] = palette.snap_to_palette(val)
                changed = True
                snapped += 1
        if changed:
            el.set("style", _serialize_style(props))
    if overridden and (saw_red or saw_green):
        report.add(
            _action(
                RuleId.NO_RAW_RGB, auto_fixed=False, message="Raw RGB left in place (override)."
            )
        )
    elif snapped:
        report.add(
            _action(
                RuleId.NO_RAW_RGB, auto_fixed=True, message=f"Snapped {snapped} raw RGB colour(s)."
            )
        )
    if saw_red and saw_green:
        report.add(
            _action(
                RuleId.NO_RED_GREEN,
                auto_fixed=not overridden,
                message="Red+green pair "
                + (
                    "left in place (override)." if overridden else "remapped to accessible colours."
                ),
            )
        )


def _is_rainbow(colors: list[str]) -> bool:
    hues = [palette.hue_deg(rgb) for c in colors if (rgb := palette.parse_color(c))]
    if len(hues) < 3:
        return False
    return min(hues) < 40 and max(hues) > 220 and any(80 < h < 160 for h in hues)


def _fix_rainbow_gradients(root, style: StyleSpec, report: StandardsReport, data_kind) -> None:
    overridden = style.is_overridden(RuleId.NO_JET)
    fixed = 0
    for grad in root.iter():
        if _local(grad) not in ("linearGradient", "radialGradient"):
            continue
        stops = [s for s in grad if _local(s) == "stop"]
        colors = [
            s.get("stop-color") or _parse_style(s.get("style")).get("stop-color", "") for s in stops
        ]
        if not _is_rainbow(colors):
            continue
        if overridden:
            report.add(
                _action(
                    RuleId.NO_JET, auto_fixed=False, message="Rainbow gradient kept (override)."
                )
            )
            continue
        repl = palette.crameri_stops(palette.replacement_colormap(data_kind), n=len(stops))
        for s, color in zip(stops, repl, strict=False):
            s.set("stop-color", color)
            props = _parse_style(s.get("style"))
            if "stop-color" in props:
                props["stop-color"] = color
                s.set("style", _serialize_style(props))
        fixed += 1
    if fixed:
        report.add(
            _action(
                RuleId.NO_JET,
                auto_fixed=True,
                message=f"Replaced {fixed} rainbow gradient(s) with Crameri.",
            )
        )


# -- BLOCK / abort ----------------------------------------------------------- #
def _check_pie(root, style: StyleSpec, report: StandardsReport, blocked: list) -> None:
    # Explicit hint OR >=3 arc-containing paths sharing an identical start point (wedges).
    explicit = False
    start_counts: dict[str, int] = {}
    for el in root.iter():
        ident = ((el.get("class") or "") + " " + (el.get("id") or "")).lower()
        if any(k in ident for k in ("pie", "donut", "wedge")):
            explicit = True
        if _local(el) == "path":
            d = el.get("d") or ""
            if "A" in d or "a" in d:
                head = d.strip()[:24]
                start_counts[head] = start_counts.get(head, 0) + 1
    wedge_cluster = any(n >= 3 for n in start_counts.values())
    if not (explicit or wedge_cluster):
        return
    if style.is_overridden(RuleId.NO_PIE):
        report.add(
            _action(
                RuleId.NO_PIE, auto_fixed=False, message="Pie kept (override) — not auto-converted."
            )
        )
        return
    blocked.append(
        _action(
            RuleId.NO_PIE,
            auto_fixed=False,
            message="Pie/donut detected: refuse. Use a sorted bar (position/length encoding). "
            "Auto-conversion to bar requires the data_plot module.",
        )
    )


def _check_fonts(root, style: StyleSpec, report: StandardsReport, blocked: list) -> None:
    floor = style.min_font_px
    overridden = style.is_overridden(RuleId.MIN_FONT)
    smallest: float | None = None
    for el in root.iter():
        if _local(el) != "text":
            continue
        size = _font_size_px(el.get("font-size") or _parse_style(el.get("style")).get("font-size"))
        if size is None or size >= floor:
            continue
        smallest = size if smallest is None else min(smallest, size)
        if overridden:
            el.set("font-size", str(floor))
    if smallest is None:
        return
    msg = f"Text {smallest:.1f}px < {style.preset.min_font_pt:g}pt floor ({floor:.1f}px)"
    if overridden:
        report.add(
            _action(RuleId.MIN_FONT, auto_fixed=True, message=msg + " — clamped (override).")
        )
    else:
        blocked.append(
            _action(
                RuleId.MIN_FONT, auto_fixed=False, message=msg + " — aborting. Increase font size."
            )
        )
