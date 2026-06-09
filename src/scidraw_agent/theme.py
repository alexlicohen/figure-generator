"""StyleSpec: the single source of truth for every silent design default.

Generators consume StyleSpec; they never hard-code style. The style_guard reads the same
spec when post-processing SVG. Journal presets carry the concrete mm / pt / dpi numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import palette


@dataclass(frozen=True)
class JournalPreset:
    """Concrete export specs for a target journal."""

    name: str
    single_col_mm: float
    double_col_mm: float
    max_height_mm: float
    min_font_pt: float
    default_font_pt: float
    min_stroke_pt: float
    colorspace: str  # "RGB" or "CMYK"
    raster_dpi: int


# Verified numbers (see docs/standards.md): Nature 89/183 mm; Cell 85/174 mm, >=7pt;
# Science 57/121 mm, CMYK at revision; eLife 300 dpi. Default = Nature double-column.
JOURNAL_PRESETS: dict[str, JournalPreset] = {
    "nature": JournalPreset("nature", 89, 183, 170, 5.0, 7.0, 0.25, "RGB", 300),
    "cell": JournalPreset("cell", 85, 174, 170, 7.0, 7.0, 0.25, "RGB", 300),
    "science": JournalPreset("science", 57, 121, 170, 5.0, 7.0, 0.25, "CMYK", 300),
    "elife": JournalPreset("elife", 85, 174, 170, 5.0, 7.0, 0.25, "RGB", 300),
}


def get_journal(name: str) -> JournalPreset:
    return JOURNAL_PRESETS.get(name.lower(), JOURNAL_PRESETS["nature"])


# Conversion: 1 pt = 1/72 in. SVG user units default to px at 96 dpi (1px = 1/96 in),
# so 1 pt = 96/72 = 4/3 px. Stroke/font floors are specified in pt and converted here.
PT_TO_PX = 96.0 / 72.0


@dataclass
class StyleSpec:
    """House style applied silently to every figure."""

    journal: str = "nature"

    # Colour
    categorical: list[str] = field(default_factory=lambda: list(palette.CATEGORICAL_ORDER))
    baseline_grey: str = palette.BASELINE_GREY

    # Data-ink
    hide_top_right_spines: bool = True
    gridline_color: str = "#B0B0B0"
    gridline_width_px: float = 0.5
    strip_shadows: bool = True
    strip_decorative_gradients: bool = False  # conservative: keep asset shading by default

    # Node rendering for flow/circuit/study-design generators:
    #   "filled"  saturated palette fill + contrast text (default)
    #   "outline" white card + coloured outline + ink text (clean, "designed" — Cohen-lab look)
    node_style: str = "filled"
    node_ink: str = "#333333"  # outline/text ink for node_style="outline"

    # Circuit generators embed a per-figure relation legend (excitatory/inhibitory/modulatory).
    # compose_panels turns this off and draws ONE combined relation legend for the whole figure,
    # so the legend isn't repeated under every panel.
    embed_relation_legend: bool = True

    # Typography (pt; converted to px via PT_TO_PX for SVG checks)
    font_family: str = "Arial, Helvetica, sans-serif"

    # Organic-asset house style: how fetched assets (neuron, brain, …) are recoloured so a
    # multi-asset figure reads as one coherent set instead of a grab-bag of source styles.
    #   "native"    keep each asset's own colours (only darken invisibly-pale achromatic ink)
    #   "grayscale" per-asset contrast-normalised neutral grey duotone (coherent monochrome)
    #   "tint"      same, in a single house ink (`asset_tint`) — a one-colour scientific plate
    asset_style: str = "native"
    asset_tint: str = "#37576B"  # muted slate-blue house ink for asset_style="tint"

    # Escape hatch: rule ids the user has explicitly opted to override. A honoured
    # override downgrades a BLOCK to a logged entry instead of aborting/auto-converting.
    allow_overrides: list[str] = field(default_factory=list)

    @property
    def preset(self) -> JournalPreset:
        return get_journal(self.journal)

    @property
    def min_font_px(self) -> float:
        return self.preset.min_font_pt * PT_TO_PX

    @property
    def default_font_px(self) -> float:
        return self.preset.default_font_pt * PT_TO_PX

    @property
    def min_stroke_px(self) -> float:
        return self.preset.min_stroke_pt * PT_TO_PX

    def is_overridden(self, rule_id: str) -> bool:
        return rule_id in self.allow_overrides


def cohen_lab(journal: str = "nature") -> StyleSpec:
    """The Cohen-lab house style: a design-focused elevation of the lab's figure conventions.

    Muted steel-blue / warm-orange categorical palette (control=blue, patient=orange); flow &
    circuit nodes as clean white cards with coloured outlines (the lab's white-box look,
    elevated); fetched anatomy normalised to a neutral grey so the accent colours carry the
    figure. Layered on a journal preset so sizing/font floors still apply.
    """
    return StyleSpec(
        journal=journal,
        categorical=list(palette.COHEN_CATEGORICAL),
        node_style="outline",
        node_ink=palette.COHEN_INK,
        asset_style="grayscale",
    )


def mpl_rcparams(style: StyleSpec) -> dict:
    """matplotlib rcParams that bake the same StyleSpec defaults into data plots.

    Same floors the SVG style_guard enforces (no top/right spines, light gridlines behind
    data, sans-serif at the journal font size, text kept as text in SVG export).
    """
    preset = style.preset
    return {
        "svg.fonttype": "none",  # keep text as text in SVG
        "pdf.fonttype": 42,  # embed real fonts in PDF
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": preset.default_font_pt,
        "axes.titlesize": preset.default_font_pt,
        "axes.labelsize": preset.default_font_pt,
        "xtick.labelsize": preset.default_font_pt,
        "ytick.labelsize": preset.default_font_pt,
        "legend.fontsize": preset.default_font_pt,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#333333",
        "axes.linewidth": max(0.5, preset.min_stroke_pt),
        "axes.axisbelow": True,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#B0B0B0",
        "grid.linewidth": 0.5,
        "lines.linewidth": 1.0,
        "figure.dpi": preset.raster_dpi,
        "savefig.bbox": "tight",
        "savefig.dpi": preset.raster_dpi,
    }
