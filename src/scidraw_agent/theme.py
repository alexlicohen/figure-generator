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

    # Typography (pt; converted to px via PT_TO_PX for SVG checks)
    font_family: str = "Arial, Helvetica, sans-serif"

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
