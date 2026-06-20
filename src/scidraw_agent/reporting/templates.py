"""The four reporting-guideline flow skeletons as ``FigureSchema`` (FigureType.REPORTING_FLOW).

Each builder reproduces the *structure* (which boxes, the spine order, where exclusion
side-boxes branch) of make-figures' canonical exemplars
(``references/exemplar_diagrams/{strobe,consort,prisma,stard}/template_input.yaml``,
Aperivue, MIT) — translated into the owned IR. Counts are *derived and validated* via the
cascade (``reporting.counts``), never typed straight into the figure; passing a ``counts``
mapping recomputes the boxes from source data and fails fast on an arithmetic mismatch.

No copyrighted checklist text is reproduced — only the node skeleton/layout (a fact).
Exclusion reasons are illustrative placeholders the caller overrides with real study data.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import Edge, Entity, EntityKind, FigureSchema, FigureType
from .counts import Cascade, FlowNode, derive_counts

# Default exemplar counts (the golden fixtures) — the figures the YAML templates ship with.
# A caller passes their own ``counts`` to fill the boxes from real data; these are the
# worked example so a template renders standalone and the goldens are reproducible.


def _spine(id: str, label: str, *, highlight: bool = False, group: str | None = None) -> Entity:
    return Entity(id=id, label=label, kind=EntityKind.COHORT, group=group, highlight=highlight)


def _side(id: str, label: str, *, beside: str) -> Entity:
    """An exclusion-reason side-box level with spine node ``beside``."""
    return Entity(id=id, label=label, kind=EntityKind.OTHER, side_box=True, rank_with=beside)


def _flow(src: str, dst: str) -> Edge:
    return Edge(source=src, target=dst, relation="flows_to")


def _exclusion(src: str, dst: str) -> Edge:
    """The dashed, arrowless, non-constraining side branch to an exclusion box."""
    return Edge(
        source=src, target=dst, relation="other",
        style="dashed", arrow=False, constraint=False,
    )


# --------------------------------------------------------------------------- #
# STROBE — observational cohort flow
# --------------------------------------------------------------------------- #
def build_strobe(counts: dict[str, int] | None = None) -> FigureSchema:
    """STROBE cohort-study participant-flow skeleton (source -> dedup -> eligible -> cohort
    -> exposed/unexposed -> outcomes), with two exclusion side-boxes."""
    c = counts or derive_counts(
        Cascade(
            {
                "source": FlowNode("source", 120000),
                "unique": FlowNode("unique", 85000),
                "eligible": FlowNode("eligible", 80000, derive_from="unique", excluded=5000),
                "cohort": FlowNode("cohort", 77500, derive_from="eligible", excluded=2500),
                "exp": FlowNode("exp", 20000),
                "unexp": FlowNode("unexp", 57500),
                "_arms": FlowNode("_arms", 77500, split=["exp", "unexp"]),
            }
        )
    )
    e = [
        _spine("source", f"Source population\n(records = {c['source']:,})"),
        _spine("unique", f"Unique subjects after deduplication\nN = {c['unique']:,}"),
        _side(
            "excl1",
            "Excluded (n = 5,000):\n• Missing age/sex\n• Outside age range",
            beside="unique",
        ),
        _spine("eligible", f"Meeting eligibility criteria\nN = {c['eligible']:,}"),
        _side(
            "excl2",
            "Excluded (n = 2,500):\n• Prior event at baseline\n• Follow-up ≤ 0 days",
            beside="eligible",
        ),
        _spine("cohort", f"Analytic cohort\nN = {c['cohort']:,}", highlight=True),
        _spine("exp", f"Exposed\nn = {c['exp']:,}", group="exposed"),
        _spine("unexp", f"Unexposed\nn = {c['unexp']:,}", group="unexposed"),
        _spine("out_exp", "Incident events\n(exposed)", group="exposed"),
        _spine("out_unexp", "Incident events\n(unexposed)", group="unexposed"),
    ]
    edges = [
        _flow("source", "unique"), _flow("unique", "eligible"), _flow("eligible", "cohort"),
        _flow("cohort", "exp"), _flow("cohort", "unexp"),
        _flow("exp", "out_exp"), _flow("unexp", "out_unexp"),
        _exclusion("unique", "excl1"), _exclusion("eligible", "excl2"),
    ]
    return FigureSchema(
        figure_type=FigureType.REPORTING_FLOW, entities=e, edges=edges,
        notes="strobe",
        caption_seed="STROBE participant-flow diagram (observational cohort).",
    )


# --------------------------------------------------------------------------- #
# CONSORT — parallel-arm RCT flow
# --------------------------------------------------------------------------- #
def build_consort(counts: dict[str, int] | None = None) -> FigureSchema:
    """CONSORT parallel-arm RCT participant-flow skeleton (assessed -> randomized ->
    two arms allocation/follow-up/analysis), with an enrollment exclusion side-box."""
    c = counts or derive_counts(
        Cascade(
            {
                "assessed": FlowNode("assessed", 500),
                "rand": FlowNode("rand", 400, derive_from="assessed", excluded=100),
                "alloc_tx": FlowNode("alloc_tx", 200),
                "alloc_ctrl": FlowNode("alloc_ctrl", 200),
                "_arms": FlowNode("_arms", 400, split=["alloc_tx", "alloc_ctrl"]),
            }
        )
    )
    e = [
        _spine("assessed", f"Assessed for eligibility\n(n = {c['assessed']:,})"),
        _side(
            "excl",
            "Excluded (n = 100):\n• Not meeting inclusion criteria\n"
            "• Declined to participate\n• Other reasons",
            beside="assessed",
        ),
        _spine("rand", f"Randomized\n(n = {c['rand']:,})", highlight=True),
        _spine(
            "alloc_tx",
            f"Allocated to intervention\n(n = {c['alloc_tx']:,})",
            group="intervention",
        ),
        _spine("alloc_ctrl", f"Allocated to control\n(n = {c['alloc_ctrl']:,})", group="control"),
        _spine("fu_tx", "Lost to follow-up\nDiscontinued intervention", group="intervention"),
        _spine("fu_ctrl", "Lost to follow-up\nDiscontinued control", group="control"),
        _spine("ana_tx", f"Analyzed\n(n = {c['alloc_tx']:,})", group="intervention"),
        _spine("ana_ctrl", f"Analyzed\n(n = {c['alloc_ctrl']:,})", group="control"),
    ]
    edges = [
        _flow("assessed", "rand"),
        _flow("rand", "alloc_tx"), _flow("rand", "alloc_ctrl"),
        _flow("alloc_tx", "fu_tx"), _flow("alloc_ctrl", "fu_ctrl"),
        _flow("fu_tx", "ana_tx"), _flow("fu_ctrl", "ana_ctrl"),
        _exclusion("assessed", "excl"),
    ]
    return FigureSchema(
        figure_type=FigureType.REPORTING_FLOW, entities=e, edges=edges,
        notes="consort",
        caption_seed="CONSORT participant-flow diagram (parallel-arm RCT).",
    )


# --------------------------------------------------------------------------- #
# PRISMA 2020 — systematic-review flow
# --------------------------------------------------------------------------- #
def build_prisma(counts: dict[str, int] | None = None) -> FigureSchema:
    """PRISMA 2020 four-phase flow skeleton (identification -> screening -> eligibility ->
    included), with three exclusion side-boxes (screen-excluded, not-retrieved, full-text
    excluded). The exclusion cascade is the canonical reporting-flow side-box pattern."""
    c = counts or derive_counts(
        Cascade(
            {
                "id_db": FlowNode("id_db", 3500),
                "id_other": FlowNode("id_other", 45),
                "dedup": FlowNode("dedup", 2700),
                "screened": FlowNode("screened", 2700),
                "ft_sought": FlowNode("ft_sought", 220, derive_from="screened", excluded=2480),
                "ft_assessed": FlowNode("ft_assessed", 208, derive_from="ft_sought", excluded=12),
                "included": FlowNode("included", 28, derive_from="ft_assessed", excluded=180),
            }
        )
    )
    e = [
        _spine("id_db", f"Records identified from databases\n(n = {c['id_db']:,})"),
        _spine("id_other", f"Records identified from other sources\n(n = {c['id_other']:,})"),
        _spine("dedup", f"Records after duplicates removed\n(n = {c['dedup']:,})"),
        _spine("screened", f"Records screened (title/abstract)\n(n = {c['screened']:,})"),
        _side("excl_ta", "Records excluded\n(n = 2,480)", beside="screened"),
        _spine("ft_sought", f"Reports sought for retrieval\n(n = {c['ft_sought']:,})"),
        _side("ft_notret", "Reports not retrieved\n(n = 12)", beside="ft_sought"),
        _spine("ft_assessed", f"Reports assessed for eligibility\n(n = {c['ft_assessed']:,})"),
        _side(
            "ft_excl",
            "Reports excluded (n = 180):\n• Wrong population\n• Wrong index test\n"
            "• Wrong outcome\n• Abstract only\n• Duplicate cohort",
            beside="ft_assessed",
        ),
        _spine("included", f"Studies included in review\n(n = {c['included']:,})", highlight=True),
    ]
    # id_other joins dedup off-spine (it identifies in parallel), so its edge does not constrain.
    edges = [
        _flow("id_db", "dedup"),
        Edge(source="id_other", target="dedup", relation="flows_to", constraint=False),
        _flow("dedup", "screened"),
        _flow("screened", "ft_sought"), _flow("ft_sought", "ft_assessed"),
        _flow("ft_assessed", "included"),
        _exclusion("screened", "excl_ta"),
        _exclusion("ft_sought", "ft_notret"),
        _exclusion("ft_assessed", "ft_excl"),
    ]
    return FigureSchema(
        figure_type=FigureType.REPORTING_FLOW, entities=e, edges=edges,
        notes="prisma",
        caption_seed="PRISMA 2020 flow diagram (systematic review).",
    )


# --------------------------------------------------------------------------- #
# STARD 2015 — diagnostic-accuracy flow
# --------------------------------------------------------------------------- #
def build_stard(counts: dict[str, int] | None = None) -> FigureSchema:
    """STARD 2015 diagnostic-accuracy flow skeleton (eligible -> index test -> reference
    standard -> index +/- -> 2×2 TP/FP/FN/TN), with an eligibility exclusion side-box."""
    c = counts or derive_counts(
        Cascade(
            {
                "eligible": FlowNode("eligible", 500),
                "index": FlowNode("index", 450, derive_from="eligible", excluded=50),
                "ref": FlowNode("ref", 450),
                "idx_pos": FlowNode("idx_pos", 180),
                "idx_neg": FlowNode("idx_neg", 270),
                "_split": FlowNode("_split", 450, split=["idx_pos", "idx_neg"]),
                "tp": FlowNode("tp", 160),
                "fp": FlowNode("fp", 20),
                "_pos": FlowNode("_pos", 180, split=["tp", "fp"]),
                "fn": FlowNode("fn", 15),
                "tn": FlowNode("tn", 255),
                "_neg": FlowNode("_neg", 270, split=["fn", "tn"]),
            }
        )
    )
    e = [
        _spine("eligible", f"Eligible patients\n(n = {c['eligible']:,})"),
        _side(
            "excl",
            "Excluded (n = 50):\n• Contraindication to index test\n"
            "• No reference standard\n• Declined",
            beside="eligible",
        ),
        _spine("index", f"Received index test\n(n = {c['index']:,})", highlight=True),
        _spine("ref", f"Received reference standard\n(n = {c['ref']:,})"),
        _spine("idx_pos", f"Index test positive\n(n = {c['idx_pos']:,})", group="positive"),
        _spine("idx_neg", f"Index test negative\n(n = {c['idx_neg']:,})", group="negative"),
        _spine("tp", f"Reference positive\nTP = {c['tp']:,}", group="positive"),
        _spine("fp", f"Reference negative\nFP = {c['fp']:,}", group="positive"),
        _spine("fn", f"Reference positive\nFN = {c['fn']:,}", group="negative"),
        _spine("tn", f"Reference negative\nTN = {c['tn']:,}", group="negative"),
    ]
    edges = [
        _flow("eligible", "index"), _flow("index", "ref"),
        _flow("ref", "idx_pos"), _flow("ref", "idx_neg"),
        _flow("idx_pos", "tp"), _flow("idx_pos", "fp"),
        _flow("idx_neg", "fn"), _flow("idx_neg", "tn"),
        _exclusion("eligible", "excl"),
    ]
    return FigureSchema(
        figure_type=FigureType.REPORTING_FLOW, entities=e, edges=edges,
        notes="stard",
        caption_seed="STARD 2015 flow diagram (diagnostic accuracy).",
    )


GUIDELINES: dict[str, Callable[[dict[str, int] | None], FigureSchema]] = {
    "strobe": build_strobe,
    "consort": build_consort,
    "prisma": build_prisma,
    "stard": build_stard,
}


def build_guideline_flow(guideline: str, counts: dict[str, int] | None = None) -> FigureSchema:
    """Build a reporting-guideline flow schema by name (strobe/consort/prisma/stard)."""
    key = guideline.strip().lower()
    if key not in GUIDELINES:
        raise ValueError(
            f"Unknown reporting guideline '{guideline}'. Known: {sorted(GUIDELINES)}"
        )
    return GUIDELINES[key](counts)
