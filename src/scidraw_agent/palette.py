"""Colour: accessible palettes, stable group mapping, colormap selection, CVD checks.

All colour defaults are CVD-safe by construction:
- categorical  -> Okabe-Ito 8-colour (Wong 2011)
- magnitude    -> Crameri batlow ; signed -> vik (zero-locked) ; cyclic -> vikO (Crameri 2020)

`PaletteRegistry` assigns each group a stable (colour, shape, linestyle) once at figure
scope so a group keeps the same encoding across every panel.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

from .models import DataKind

# Okabe-Ito colourblind-safe categorical palette (hex). Wong 2011, Nat Methods.
OKABE_ITO: dict[str, str] = {
    "black": "#000000",
    "orange": "#E69F00",
    "sky_blue": "#56B4E9",
    "bluish_green": "#009E73",
    "yellow": "#F0E442",
    "blue": "#0072B2",
    "vermillion": "#D55E00",
    "reddish_purple": "#CC79A7",
}

# Assignment order favours high-contrast, distinguishable hues first; black last
# (it reads as "ink" rather than a category). Yellow is low-contrast on white -> late.
CATEGORICAL_ORDER: list[str] = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#56B4E9",  # sky blue
    "#D55E00",  # vermillion
    "#000000",  # black
    "#F0E442",  # yellow
]

# Cohen-lab house palette: a muted, cohesive system built around the steel-blue / warm-orange
# pairing seen across the lab's figures (control/NT = blue, patient = orange). Blue+orange is
# colourblind-safe; the secondary hues are kept muted so accents read as a designed set.
COHEN_CATEGORICAL: list[str] = [
    "#2F5C8A",  # steel blue   (primary accent / control)
    "#D97A1E",  # warm orange  (secondary / patient)
    "#3E8E7E",  # muted teal
    "#8E4B6E",  # muted plum
    "#5B6B7B",  # slate
    "#A8862E",  # muted gold
]
COHEN_INK = "#222831"  # near-black for outlines / text

# Muted grey reserved for baselines/controls; saturated colour is for emphasis.
BASELINE_GREY = "#999999"
BASELINE_GROUP_NAMES = {
    "control",
    "controls",
    "baseline",
    "sham",
    "vehicle",
    "wt",
    "wild-type",
    "wildtype",
    "healthy",
    "ctrl",
}

# Redundant-encoding cycles (colour is never the only channel).
SHAPE_CYCLE = ["circle", "square", "triangle", "diamond", "cross", "star", "hexagon", "wye"]
LINESTYLE_CYCLE = ["solid", "dashed", "dotted", "dashdot"]

# Crameri colormaps by data kind (cmcrameri names, usable as 'cmc.<name>' in matplotlib).
CRAMERI_BY_KIND: dict[DataKind, str] = {
    DataKind.MAGNITUDE: "cmc.batlow",
    DataKind.SIGNED: "cmc.vik",
    DataKind.CYCLIC: "cmc.vikO",
}

# Perceptually non-uniform / rainbow maps that must never encode data.
BANNED_COLORMAPS = {
    "jet",
    "rainbow",
    "gist_rainbow",
    "hsv",
    "turbo",
    "nipy_spectral",
    "parula",
}

# Pure primaries (and CSS names) that must be snapped to the accessible palette.
_RAW_PRIMARIES: dict[str, tuple[int, int, int]] = {
    "#ff0000": (255, 0, 0),
    "#f00": (255, 0, 0),
    "red": (255, 0, 0),
    "#00ff00": (0, 255, 0),
    "#0f0": (0, 255, 0),
    "lime": (0, 255, 0),
    "green": (0, 128, 0),
    "#0000ff": (0, 0, 255),
    "#00f": (0, 0, 255),
    "blue": (0, 0, 255),
}

_NAMED_COLORS = {
    "red": (255, 0, 0),
    "lime": (0, 255, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "magenta": (255, 0, 255),
    "cyan": (0, 255, 255),
    "yellow": (255, 255, 0),
}


# --------------------------------------------------------------------------- #
# Colour parsing helpers
# --------------------------------------------------------------------------- #
def parse_color(value: str) -> tuple[int, int, int] | None:
    """Parse a hex / named / rgb() colour into an (r, g, b) 0-255 tuple, else None."""
    if not value:
        return None
    v = value.strip().lower()
    if v in _NAMED_COLORS:
        return _NAMED_COLORS[v]
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                return None
    if v.startswith("rgb(") and v.endswith(")"):
        try:
            parts = [p.strip() for p in v[4:-1].split(",")]
            return tuple(
                int(round(float(p.rstrip("%")) * (2.55 if "%" in p else 1))) for p in parts
            )  # type: ignore[return-value]
        except (ValueError, IndexError):
            return None
    return None


def is_raw_primary(value: str) -> bool:
    """True if the colour is a pure RGB primary (or its CSS name)."""
    if not value:
        return False
    return value.strip().lower() in _RAW_PRIMARIES


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def hue_deg(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255 for c in rgb)
    return colorsys.rgb_to_hls(r, g, b)[0] * 360.0


# --------------------------------------------------------------------------- #
# Perceptual distance / CVD
# --------------------------------------------------------------------------- #
def _to_ucs(rgb: tuple[int, int, int], cvd_type: str | None = None):
    """Convert sRGB 0-255 to CAM02-UCS, optionally simulating a CVD type first."""
    from colorspacious import cspace_convert

    rgb01 = [c / 255 for c in rgb]
    if cvd_type:
        space = {"name": "sRGB1+CVD", "cvd_type": cvd_type, "severity": 100}
        rgb01 = cspace_convert(rgb01, space, "sRGB1")
    return cspace_convert(rgb01, "sRGB1", "CAM02-UCS")


def cvd_min_distance(colors: list[str], cvd_type: str = "deuteranomaly") -> float:
    """Minimum pairwise CAM02-UCS distance after simulating ``cvd_type``.

    Values below ~15 indicate two colours that a viewer with that CVD cannot reliably
    distinguish. Returns inf for <2 parseable colours.
    """
    import math

    pts = [_to_ucs(rgb, cvd_type) for c in colors if (rgb := parse_color(c))]
    if len(pts) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            d = math.dist(pts[i], pts[j])
            best = min(best, d)
    return best


def snap_to_palette(value: str) -> str:
    """Return the nearest Okabe-Ito colour to ``value`` (by CAM02-UCS distance)."""
    import math

    rgb = parse_color(value)
    if rgb is None:
        return CATEGORICAL_ORDER[0]
    target = _to_ucs(rgb)
    best_hex, best_d = CATEGORICAL_ORDER[0], float("inf")
    for hexv in OKABE_ITO.values():
        d = math.dist(target, _to_ucs(parse_color(hexv)))  # type: ignore[arg-type]
        if d < best_d:
            best_hex, best_d = hexv, d
    return best_hex


# --------------------------------------------------------------------------- #
# Colormap selection
# --------------------------------------------------------------------------- #
def colormap_for(data_kind: DataKind) -> str | None:
    """Return the Crameri colormap name for a data kind, or None for categorical/none."""
    return CRAMERI_BY_KIND.get(data_kind)


def replacement_colormap(data_kind: DataKind | None = None) -> str:
    """Crameri replacement for a banned (rainbow) colormap.

    Defaults to diverging ``vik`` when the data kind is unknown — a generic colorbar is
    safest read as signed/centred; generators pass the real ``data_kind`` for precision.
    """
    if data_kind and data_kind in CRAMERI_BY_KIND:
        return CRAMERI_BY_KIND[data_kind]
    return "cmc.vik"


def crameri_stops(name: str, n: int = 5) -> list[str]:
    """Sample ``n`` hex stops from a Crameri colormap (for replacing rainbow gradients)."""
    short = name.split(".", 1)[-1]
    try:
        from cmcrameri import cm

        cmap = getattr(cm, short)
    except (ImportError, AttributeError):  # pragma: no cover - fallback ramp (vik-like)
        return ["#001261", "#3a5fcd", "#f7f7f7", "#cd5b45", "#5a0a0a"][:n]
    out = []
    for i in range(n):
        r, g, b, _ = cmap(i / (n - 1) if n > 1 else 0.0)
        out.append(_hex((round(r * 255), round(g * 255), round(b * 255))))
    return out


# --------------------------------------------------------------------------- #
# Stable per-figure group mapping
# --------------------------------------------------------------------------- #
@dataclass
class GroupStyle:
    color: str
    shape: str
    linestyle: str


@dataclass
class PaletteRegistry:
    """Assigns and remembers a stable (colour, shape, linestyle) per group.

    ``colors`` overrides the categorical colour order (e.g. a lab house palette); it defaults
    to the Okabe-Ito order so existing behaviour is unchanged.
    """

    mapping: dict[str, GroupStyle] = field(default_factory=dict)
    colors: list[str] = field(default_factory=lambda: list(CATEGORICAL_ORDER))
    _next: int = 0

    def assign(self, group: str) -> GroupStyle:
        """Return the stable style for ``group``, allocating a new slot if first seen.

        Baseline/control groups get muted grey; every other group gets the next
        distinguishable categorical colour. Existing groups are never recoloured.
        """
        if group in self.mapping:
            return self.mapping[group]
        if group.strip().lower() in BASELINE_GROUP_NAMES:
            style = GroupStyle(BASELINE_GREY, SHAPE_CYCLE[0], LINESTYLE_CYCLE[0])
        else:
            idx = self._next
            self._next += 1
            colors = self.colors or list(CATEGORICAL_ORDER)
            style = GroupStyle(
                colors[idx % len(colors)],
                SHAPE_CYCLE[idx % len(SHAPE_CYCLE)],
                LINESTYLE_CYCLE[idx % len(LINESTYLE_CYCLE)],
            )
        self.mapping[group] = style
        return style

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {g: vars(s) for g, s in self.mapping.items()}
