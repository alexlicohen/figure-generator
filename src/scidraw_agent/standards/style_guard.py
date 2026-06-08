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
    _strip_hatch(root, style, report)
    _snap_colors(elements, style, report)
    _fix_rainbow_gradients(root, style, report, data_kind)
    _check_pie(root, style, report, blocked)
    _check_3d(root, style, report, blocked)
    _check_tick_density(root, style, report)
    _check_bubble_area(root, style, report)
    _check_text_contrast(root, style, report)
    _check_abbreviations(root, style, report)
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


# -- pie -> bar (Cleveland & McGill: position/length beats angle/area) -------- #
_MOVE_RE = re.compile(r"^\s*[Mm]\s*(-?[\d.]+)[\s,]+(-?[\d.]+)")
# Point immediately before the (first) elliptical-arc command = the wedge's first rim point.
_PREARC_RE = re.compile(r"(-?[\d.]+)[\s,]+(-?[\d.]+)\s*[Aa]")
# A rx ry x-rot large-arc sweep x y  (flags may or may not be space-separated).
_ARC_RE = re.compile(
    r"[Aa]\s*[\d.]+[\s,]+[\d.]+[\s,]+[\d.eE+-]+[\s,]*([01])[\s,]*([01])[\s,]*"
    r"(-?[\d.]+)[\s,]+(-?[\d.]+)"
)


def _arc_center(d: str) -> tuple[float, float] | None:
    m = _MOVE_RE.match(d)
    return (float(m.group(1)), float(m.group(2))) if m else None


def _recover_wedge(d: str, cx: float, cy: float) -> tuple[float, float] | None:
    """Return (fraction_of_circle, radius) for one wedge arc path, or None if unparseable."""
    import math

    pre = _PREARC_RE.search(d)
    arc = _ARC_RE.search(d)
    if not (pre and arc):
        return None
    p1 = (float(pre.group(1)), float(pre.group(2)))
    large = arc.group(1) == "1"
    p2 = (float(arc.group(3)), float(arc.group(4)))
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    a2 = math.atan2(p2[1] - cy, p2[0] - cx)
    raw = (a2 - a1) % (2 * math.pi)
    swept = max(raw, 2 * math.pi - raw) if large else min(raw, 2 * math.pi - raw)
    radius = math.hypot(p1[0] - cx, p1[1] - cy)
    return swept / (2 * math.pi), radius


def _check_pie(root, style: StyleSpec, report: StandardsReport, blocked: list) -> None:
    # Explicit hint OR >=3 arc paths sharing a centre point (wedges of one pie).
    explicit = False
    by_center: dict[tuple[float, float], list] = {}
    for el in root.iter():
        ident = ((el.get("class") or "") + " " + (el.get("id") or "")).lower()
        if any(k in ident for k in ("pie", "donut", "wedge")):
            explicit = True
        if _local(el) == "path":
            d = el.get("d") or ""
            if "A" in d or "a" in d:
                c = _arc_center(d)
                if c is not None:
                    by_center.setdefault((round(c[0], 1), round(c[1], 1)), []).append(el)
    cluster = max(by_center.items(), key=lambda kv: len(kv[1]), default=(None, []))
    wedges = cluster[1] if len(cluster[1]) >= 3 else []
    if not (explicit or wedges):
        return

    if style.is_overridden(RuleId.NO_PIE):
        report.add(
            _action(
                RuleId.NO_PIE, auto_fixed=False, message="Pie kept (override) — not auto-converted."
            )
        )
        return

    # Recover per-wedge fractions from arc geometry; convert to a sorted horizontal bar.
    cx, cy = cluster[0] if cluster[0] is not None else (0.0, 0.0)
    recovered = []
    for el in wedges:
        rec = _recover_wedge(el.get("d") or "", cx, cy)
        if rec is not None:
            fill = (el.get("fill") or _parse_style(el.get("style")).get("fill") or "").strip()
            recovered.append((rec[0], rec[1], fill, el))
    if len(recovered) >= 2:
        _convert_pie_to_bar(root, cx, cy, recovered, style)
        report.add(
            _action(
                RuleId.NO_PIE,
                auto_fixed=True,
                message=f"Pie/donut auto-converted to a sorted horizontal bar "
                f"({len(recovered)} slices) — position/length encoding.",
            )
        )
        return

    # Detected a pie but could not recover slice values (e.g. non-arc wedges) -> refuse.
    blocked.append(
        _action(
            RuleId.NO_PIE,
            auto_fixed=False,
            message="Pie/donut detected but slice values not recoverable: refuse. "
            "Use a sorted bar (position/length encoding).",
        )
    )


def _convert_pie_to_bar(root, cx, cy, recovered, style: StyleSpec) -> None:
    """Replace wedge paths with a sorted (descending) horizontal bar chart in their place."""
    radius = max((r for _, r, _, _ in recovered), default=40.0) or 40.0
    total = sum(f for f, _, _, _ in recovered) or 1.0

    # remove the wedge paths and any text that sat on top of the pie (slice labels)
    parent = None
    for _, _, _, el in recovered:
        p = el.getparent()
        if parent is None:
            parent = p
        if p is not None:
            p.remove(el)
    for txt in list(root.iter()):
        if _local(txt) != "text":
            continue
        tx, ty = _num(txt.get("x")), _num(txt.get("y"))
        if tx is None or ty is None:
            continue
        if abs(tx - cx) <= radius and abs(ty - cy) <= radius:
            tp = txt.getparent()
            if tp is not None:
                tp.remove(txt)
    if parent is None:
        parent = root

    # layout: bars fill the pie's bounding box, sorted largest-first
    slices = sorted(recovered, key=lambda t: t[0], reverse=True)
    x0, top = cx - radius, cy - radius
    height = 2 * radius
    bar_max = 1.4 * radius  # leave room for the % label to the right
    row_h = height / len(slices)
    bar_h = row_h * 0.62
    nsg = "{http://www.w3.org/2000/svg}"
    grp = etree.SubElement(parent, f"{nsg}g")
    grp.set("class", "pie-converted-bar")
    for i, (frac, _r, fill, _el) in enumerate(slices):
        pct = 100.0 * frac / total
        y = top + i * row_h + (row_h - bar_h) / 2
        if fill and fill.lower() not in _WHITE:
            color = fill
        else:
            color = palette.CATEGORICAL_ORDER[i % len(palette.CATEGORICAL_ORDER)]
        biggest = max((s[0] for s in slices), default=0.0) or 1.0  # avoid /0 on degenerate pies
        rect = etree.SubElement(grp, f"{nsg}rect")
        rect.set("x", f"{x0:g}")
        rect.set("y", f"{y:g}")
        rect.set("width", f"{bar_max * frac / biggest:g}")
        rect.set("height", f"{bar_h:g}")
        rect.set("fill", color)
        label = etree.SubElement(grp, f"{nsg}text")
        label.set("x", f"{x0 + 3:g}")
        label.set("y", f"{y + bar_h * 0.5 + style.default_font_px * 0.35:g}")
        label.set("font-size", f"{style.default_font_px:g}")
        label.set("font-family", style.font_family)
        label.set("fill", "#000000")
        label.text = f"{pct:.0f}%"


# -- Tier-2 standards (PLAN §5b) --------------------------------------------- #
_URL_REF = re.compile(r"url\(#([^)]+)\)")
_ABBREV = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
_TICK_ID = re.compile(r"^[xy]tick_\d+$")
# Always-understood / handled-elsewhere tokens that need no caption definition.
_ABBREV_OK = {"L", "R", "NS", "ID", "OK", "MRI", "DNA", "RNA", "AP", "ML", "DV"}
# Whole-token 3D markers (faux-3D on 2D data). Never matched as substrings (hex-id safe).
_3D_VOCAB = {"axes3d", "mplot3d", "bar3d", "pie3d", "surf3d", "surface3d", "scatter3d"}


def _check_3d(root, style: StyleSpec, report: StandardsReport, blocked: list) -> None:
    """Block faux-3D on 2D data (3D axes, or a shear transform that fakes perspective).

    Matches only a fixed 3D vocabulary as whole tokens — never an arbitrary "3d" substring,
    because matplotlib emits random hex ids (e.g. ``p23d8f``) that would otherwise false-fire.
    """
    found = False
    for el in root.iter():
        cls = set(re.split(r"[^a-z0-9]+", (el.get("class") or "").lower()))
        ids = set(re.split(r"[^a-z0-9]+", (el.get("id") or "").lower()))
        # class tokens aren't hex, so a bare "3d" class is a genuine signal; ids only match the
        # multi-letter vocab (which can never collide with a hex string).
        if (cls & (_3D_VOCAB | {"3d"})) or (ids & _3D_VOCAB):
            found = True
        transform = (el.get("transform") or "") + _parse_style(el.get("style")).get("transform", "")
        if "skewx" in transform.lower() or "skewy" in transform.lower():
            found = True
    if not found:
        return
    if style.is_overridden(RuleId.NO_3D):
        report.add(
            _action(RuleId.NO_3D, auto_fixed=False, message="3D/perspective kept (override).")
        )
        return
    blocked.append(
        _action(
            RuleId.NO_3D,
            auto_fixed=False,
            message="3D/perspective effect on 2D data detected — render it flat (BLOCK).",
        )
    )


def _strip_hatch(root, style: StyleSpec, report: StandardsReport) -> None:
    """Replace hatch/pattern fills with a representative solid colour, drop the pattern defs."""
    patterns: dict[str, str] = {}
    for el in root.iter():
        if _local(el) != "pattern" or not el.get("id"):
            continue
        color = None
        for child in el.iter():
            c = (
                child.get("stroke")
                or child.get("fill")
                or _parse_style(child.get("style")).get("stroke")
                or _parse_style(child.get("style")).get("fill")
            )
            if c and c.strip().lower() not in _WHITE:
                color = c.strip()
                break
        patterns[el.get("id")] = color or palette.CATEGORICAL_ORDER[0]
    if not patterns:
        return
    fixed = 0
    for el in root.iter():
        for attr in ("fill", "stroke"):
            m = _URL_REF.match((el.get(attr) or "").strip())
            if m and m.group(1) in patterns:
                el.set(attr, patterns[m.group(1)])
                fixed += 1
        props = _parse_style(el.get("style"))
        changed = False
        for k in ("fill", "stroke"):
            m = _URL_REF.match((props.get(k) or "").strip())
            if m and m.group(1) in patterns:
                props[k] = patterns[m.group(1)]
                changed = True
                fixed += 1
        if changed:
            el.set("style", _serialize_style(props))
    for el in list(root.iter()):
        if _local(el) == "pattern" and el.get("id") in patterns:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
    if fixed:
        report.add(
            _action(
                RuleId.NO_HATCH,
                auto_fixed=True,
                message=f"Replaced {fixed} hatch/pattern fill(s) with a solid colour.",
            )
        )


def _check_tick_density(root, style: StyleSpec, report: StandardsReport) -> None:
    """Warn when an axis carries many ticks (matplotlib emits id='xtick_N' / 'ytick_N')."""
    counts = {"x": 0, "y": 0}
    for el in root.iter():
        m = _TICK_ID.match(el.get("id") or "")
        if m:
            counts[(el.get("id") or "")[0]] += 1
    busy = {ax: c for ax, c in counts.items() if c > 12}
    if busy:
        detail = ", ".join(f"{ax}-axis {c} ticks" for ax, c in busy.items())
        report.add(
            _action(
                RuleId.TICK_DENSITY,
                auto_fixed=False,
                message=f"Dense axis ticks ({detail}) — thin to ~5–7 labelled ticks.",
            )
        )


def _check_bubble_area(root, style: StyleSpec, report: StandardsReport) -> None:
    """Warn on a bubble chart (>=5 distinct circle radii) to confirm area-proportional sizing."""
    radii = {
        round(r, 2)
        for el in root.iter()
        if _local(el) == "circle" and (r := _num(el.get("r")))
    }
    if len(radii) >= 5:
        report.add(
            _action(
                RuleId.BUBBLE_AREA,
                auto_fixed=False,
                message=f"{len(radii)} distinct bubble radii — size must encode by AREA "
                "(radius ∝ √value), not radius.",
            )
        )


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _check_text_contrast(root, style: StyleSpec, report: StandardsReport) -> None:
    """Warn on text whose colour is below the 4.5:1 WCAG-AA floor against the white background."""
    bad: set[str] = set()
    for el in root.iter():
        if _local(el) != "text":
            continue
        fill = el.get("fill") or _parse_style(el.get("style")).get("fill")
        if not fill or fill.strip().lower() in _WHITE:
            continue
        rgb = palette.parse_color(fill)
        if not rgb:
            continue
        contrast = 1.05 / (_relative_luminance(rgb) + 0.05)
        if contrast < 4.5:
            bad.add(fill.strip())
    if bad:
        report.add(
            _action(
                RuleId.TEXT_CONTRAST,
                auto_fixed=False,
                message=f"Low-contrast text vs white (<4.5:1 WCAG AA): {', '.join(sorted(bad))}.",
            )
        )


def _check_abbreviations(root, style: StyleSpec, report: StandardsReport) -> None:
    """Warn (advisory) when >=3 distinct abbreviations appear, to prompt a caption legend."""
    toks: set[str] = set()
    for el in root.iter():
        if _local(el) != "text" or not el.text:
            continue
        toks |= {t for t in _ABBREV.findall(el.text) if t not in _ABBREV_OK}
    if len(toks) >= 3:
        report.add(
            _action(
                RuleId.ABBREVIATION_LEGEND,
                auto_fixed=False,
                message=f"Define these abbreviations in the caption: {', '.join(sorted(toks))}.",
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
