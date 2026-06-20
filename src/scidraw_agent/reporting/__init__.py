"""Reporting-guideline participant-flow skeletons + count derivation.

This package translates the four canonical reporting-guideline flow diagrams
(STROBE, CONSORT, PRISMA 2020, STARD 2015) into the owned ``FigureSchema`` IR, and derives /
validates the ``(n=…)`` box counts from source data rather than letting them be invented.

ATTRIBUTION
-----------
The node skeletons (which boxes, in what order, branching where) and the count-derivation /
cascade-reconciliation logic are reimplemented from the *make-figures* skill
(Aperivue, MIT) — specifically its ``references/exemplar_diagrams/{strobe,consort,prisma,
stard}/template_input.yaml`` layouts and ``scripts/derive_figure_legend_counts.py`` /
``fill_prisma_template.py``. Only the structure (fact/layout) is reused; no copyrighted
checklist text is reproduced. See ``NOTICE`` at the repo root.

The four builders return a ``FigureSchema`` of ``FigureType.REPORTING_FLOW``: spine boxes
plus dashed, arrowless, ``constraint=false`` exclusion side-boxes (``Entity.side_box`` +
``Entity.rank_with``), rendered by the existing Graphviz pipeline generator — one owner of
flow rendering, no separate flow engine.
"""

from __future__ import annotations

from .counts import (
    CountValidationError,
    derive_counts,
    extract_counts,
    fill_template,
    validate_cascade,
)
from .templates import (
    GUIDELINES,
    build_consort,
    build_guideline_flow,
    build_prisma,
    build_stard,
    build_strobe,
)

__all__ = [
    "CountValidationError",
    "derive_counts",
    "extract_counts",
    "fill_template",
    "validate_cascade",
    "GUIDELINES",
    "build_guideline_flow",
    "build_strobe",
    "build_consort",
    "build_prisma",
    "build_stard",
]
