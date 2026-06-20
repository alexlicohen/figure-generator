"""The rule catalog: RuleId -> (tier, message, source_url).

This is the single registry of design-standards rules. `style_guard` references rules by
id when it applies a fix or records a warning/override, so the manifest's `standards` block
always carries the rule id and its authoritative source. `docs/standards.md` mirrors this.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..models import StandardsTier

# Numeric thresholds adopted from make-figures' critic_figure.py (Aperivue, MIT). The raster
# critic OCR'd a rendered PNG; we apply the same *values* structurally on the SVG (no OCR /
# raster step — the SVG standards engine already reads font sizes and fills directly).
MIN_READABLE_PX = 14.0  # smallest comfortably-readable text at print scale (critic_figure)
OUT_OF_PALETTE_TOLERANCE = 0.15  # max fraction of distinct fills allowed off the house palette


class RuleId(StrEnum):
    # Colour
    NO_JET = "no_jet"
    NO_RAW_RGB = "no_raw_rgb"
    NO_RED_GREEN = "no_red_green"
    CVD_DISTANCE = "cvd_distance"
    # Data-ink
    NO_SHADOWS = "no_shadows"
    NO_FRAME = "no_frame"
    GRIDLINE_DEMOTE = "gridline_demote"
    NO_3D = "no_3d"
    NO_HATCH = "no_hatch"
    TICK_DENSITY = "tick_density"
    BUBBLE_AREA = "bubble_area"
    TEXT_CONTRAST = "text_contrast"
    ABBREVIATION_LEGEND = "abbreviation_legend"
    GROUP_SHAPE = "group_shape"
    # Decoding hierarchy
    NO_PIE = "no_pie"
    # Distribution rigor (data_plot)
    NO_DYNAMITE = "no_dynamite"
    DISTRIBUTION_GEOM = "distribution_geom"
    OVERPLOT_ALPHA = "overplot_alpha"
    SUPERPLOT = "superplot"
    STAT_REPORTING = "stat_reporting"
    # Typography / layout
    MIN_FONT = "min_font"
    READABLE_FONT = "readable_font"
    MIN_STROKE = "min_stroke"
    # Palette discipline (raster-critic thresholds adopted structurally)
    OUT_OF_PALETTE = "out_of_palette"
    # Content fidelity
    SOURCE_COVERAGE = "source_coverage"
    # Neuro integrity
    NEURO_DECLINE = "neuro_decline"
    BRAIN_ORIENTATION = "brain_orientation"


@dataclass(frozen=True)
class Rule:
    id: RuleId
    tier: StandardsTier
    message: str
    source_url: str


RULES: dict[RuleId, Rule] = {
    RuleId.NO_JET: Rule(
        RuleId.NO_JET,
        StandardsTier.BLOCK,
        "Rainbow/jet colormap replaced with a perceptually-uniform Crameri map.",
        "https://www.nature.com/articles/s41467-020-19160-7",
    ),
    RuleId.NO_RAW_RGB: Rule(
        RuleId.NO_RAW_RGB,
        StandardsTier.BLOCK,
        "Raw primary RGB snapped to the nearest Okabe-Ito colour.",
        "https://www.nature.com/articles/nmeth.1618",
    ),
    RuleId.NO_RED_GREEN: Rule(
        RuleId.NO_RED_GREEN,
        StandardsTier.BLOCK,
        "Red/green-only contrast remapped to a colourblind-safe pair.",
        "https://www.nature.com/articles/nmeth.1618",
    ),
    RuleId.CVD_DISTANCE: Rule(
        RuleId.CVD_DISTANCE,
        StandardsTier.WARN,
        "Two colours are too close under simulated colour-vision deficiency.",
        "https://www.nature.com/articles/nmeth.1618",
    ),
    RuleId.NO_SHADOWS: Rule(
        RuleId.NO_SHADOWS,
        StandardsTier.DEFAULT,
        "Drop shadows / bevel filters stripped (maximise data-ink).",
        "https://infovis-wiki.net/wiki/Data-Ink_Ratio",
    ),
    RuleId.NO_FRAME: Rule(
        RuleId.NO_FRAME,
        StandardsTier.DEFAULT,
        "Full-canvas background/frame removed (no redundant bounding box).",
        "https://seaborn.pydata.org/tutorial/aesthetics.html",
    ),
    RuleId.GRIDLINE_DEMOTE: Rule(
        RuleId.GRIDLINE_DEMOTE,
        StandardsTier.DEFAULT,
        "Gridlines demoted to light grey behind data.",
        "https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.grid.html",
    ),
    RuleId.NO_3D: Rule(
        RuleId.NO_3D,
        StandardsTier.BLOCK,
        "3D/perspective effect on 2D data — flatten it (3D distorts length/area judgements).",
        "https://www.data-to-viz.com/caveat/3d.html",
    ),
    RuleId.NO_HATCH: Rule(
        RuleId.NO_HATCH,
        StandardsTier.DEFAULT,
        "Hatch/pattern fill replaced with a solid colour (hatching causes moiré, hurts print).",
        "https://www.data-to-viz.com/caveat.html",
    ),
    RuleId.TICK_DENSITY: Rule(
        RuleId.TICK_DENSITY,
        StandardsTier.WARN,
        "Axis has many ticks — thin to ~5–7 labelled ticks to cut clutter.",
        "https://matplotlib.org/stable/api/ticker_api.html",
    ),
    RuleId.BUBBLE_AREA: Rule(
        RuleId.BUBBLE_AREA,
        StandardsTier.WARN,
        "Bubble size must encode by AREA (radius ∝ √value), not radius, or values look inflated.",
        "https://www.data-to-viz.com/caveat/radius_or_area.html",
    ),
    RuleId.TEXT_CONTRAST: Rule(
        RuleId.TEXT_CONTRAST,
        StandardsTier.WARN,
        "Text colour falls below the 4.5:1 WCAG-AA contrast floor against white.",
        "https://www.w3.org/TR/WCAG21/#contrast-minimum",
    ),
    RuleId.ABBREVIATION_LEGEND: Rule(
        RuleId.ABBREVIATION_LEGEND,
        StandardsTier.WARN,
        "Figure uses abbreviations — define them in the caption or a legend key.",
        "https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/",
    ),
    RuleId.GROUP_SHAPE: Rule(
        RuleId.GROUP_SHAPE,
        StandardsTier.BLOCK,
        "Overlapping groups carry a redundant marker shape, not colour alone (colour-blind safe).",
        "https://www.nature.com/articles/nmeth.1618",
    ),
    RuleId.NO_PIE: Rule(
        RuleId.NO_PIE,
        StandardsTier.BLOCK,
        "Pie/donut auto-converted to a sorted horizontal bar (position/length encoding); "
        "refused only when slice values cannot be recovered.",
        "https://www.informationvisuals.com/information-design-theory/elementary-perceptual-tasks",
    ),
    RuleId.NO_DYNAMITE: Rule(
        RuleId.NO_DYNAMITE,
        StandardsTier.BLOCK,
        "Bar+SEM 'dynamite' plot for continuous data — show the data distribution instead.",
        "https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1002128",
    ),
    RuleId.DISTRIBUTION_GEOM: Rule(
        RuleId.DISTRIBUTION_GEOM,
        StandardsTier.DEFAULT,
        "Distribution geometry chosen by sample size (dots / box+points / violin).",
        "https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1002128",
    ),
    RuleId.OVERPLOT_ALPHA: Rule(
        RuleId.OVERPLOT_ALPHA,
        StandardsTier.DEFAULT,
        "Point opacity scaled to sample size to manage overplotting.",
        "https://clauswilke.com/dataviz/overlapping-points.html",
    ),
    RuleId.SUPERPLOT: Rule(
        RuleId.SUPERPLOT,
        StandardsTier.DEFAULT,
        "Nested replicates shown as a SuperPlot (points by replicate, replicate means).",
        "https://rupress.org/jcb/article/219/6/e202001064/151717",
    ),
    RuleId.STAT_REPORTING: Rule(
        RuleId.STAT_REPORTING,
        StandardsTier.DEFAULT,
        "Significance shown with exact p-value, n, and an effect size — not asterisks alone.",
        "https://www.nature.com/articles/nphys4031",
    ),
    RuleId.MIN_FONT: Rule(
        RuleId.MIN_FONT,
        StandardsTier.BLOCK,
        "Text below the journal minimum font size.",
        "https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/",
    ),
    RuleId.READABLE_FONT: Rule(
        RuleId.READABLE_FONT,
        StandardsTier.WARN,
        f"Text below the {MIN_READABLE_PX:g}px comfortably-readable threshold (above the hard "
        "journal floor but small for a flow/abstract at print scale).",
        "https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/",
    ),
    RuleId.OUT_OF_PALETTE: Rule(
        RuleId.OUT_OF_PALETTE,
        StandardsTier.WARN,
        f">{OUT_OF_PALETTE_TOLERANCE:.0%} of distinct fills fall outside the colour-blind-safe "
        "house palette — colours not in the palette may not be CVD-distinguishable.",
        "https://www.nature.com/articles/nmeth.1618",
    ),
    RuleId.SOURCE_COVERAGE: Rule(
        RuleId.SOURCE_COVERAGE,
        StandardsTier.WARN,
        "Figure labels cover few of the salient source words — content the source supports may "
        "be missing (coverage check, no OCR).",
        "https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1003833",
    ),
    RuleId.MIN_STROKE: Rule(
        RuleId.MIN_STROKE,
        StandardsTier.DEFAULT,
        "Hairline stroke clamped to the minimum printable weight.",
        "https://scholarviz.com/blog/journal-target-size-dpi-font-decision-tree",
    ),
    RuleId.NEURO_DECLINE: Rule(
        RuleId.NEURO_DECLINE,
        StandardsTier.BLOCK,
        "Real neuroimaging render requested — use nilearn / FSLeyes / MRIcroGL / Surf Ice.",
        "https://apertureneuro.org/article/85104",
    ),
    RuleId.BRAIN_ORIENTATION: Rule(
        RuleId.BRAIN_ORIENTATION,
        StandardsTier.BLOCK,
        "Brain panel must declare orientation (neurological/radiological) with L/R markers.",
        "https://nipy.org/nibabel/neuro_radio_conventions.html",
    ),
}


def rule(rule_id: RuleId) -> Rule:
    return RULES[rule_id]
