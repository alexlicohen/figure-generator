"""The rule catalog: RuleId -> (tier, message, source_url).

This is the single registry of design-standards rules. `style_guard` references rules by
id when it applies a fix or records a warning/override, so the manifest's `standards` block
always carries the rule id and its authoritative source. `docs/standards.md` mirrors this.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..models import StandardsTier


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
    # Decoding hierarchy
    NO_PIE = "no_pie"
    # Distribution rigor (data_plot)
    NO_DYNAMITE = "no_dynamite"
    DISTRIBUTION_GEOM = "distribution_geom"
    OVERPLOT_ALPHA = "overplot_alpha"
    SUPERPLOT = "superplot"
    # Typography / layout
    MIN_FONT = "min_font"
    MIN_STROKE = "min_stroke"
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
    RuleId.MIN_FONT: Rule(
        RuleId.MIN_FONT,
        StandardsTier.BLOCK,
        "Text below the journal minimum font size.",
        "https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/",
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
