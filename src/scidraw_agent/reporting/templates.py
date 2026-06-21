"""The four reporting-guideline flow skeletons as ``FigureSchema`` (FigureType.REPORTING_FLOW).

Each builder reproduces the *structure* (which boxes, the spine order, where exclusion
side-boxes branch) of make-figures' canonical exemplars
(``references/exemplar_diagrams/{strobe,consort,prisma,stard}/template_input.yaml``,
Aperivue, MIT) — translated into the owned IR. Counts are *derived and validated* via the
cascade (``reporting.counts``), never typed straight into the figure.

THE INVARIANT (and how it is enforced for BOTH branches):

  * Each guideline defines its cascade TOPOLOGY once — the ``derive_from`` / ``excluded`` /
    ``split`` wiring, independent of the numbers — plus a worked exemplar's numbers.
  * The box ``count`` is taken from the caller's ``counts`` dict when supplied, else from the
    exemplar, and is ALWAYS fed through ``derive_counts(cascade)`` so ``validate_cascade``
    runs whether or not the caller passed counts. A caller dict whose arms don't sum to the
    parent, or whose waterfall doesn't reconcile, fails fast — it is never rendered.
  * Every box label is filled via ``fill_template(template, counts)`` with ``{key}``
    placeholders, so a missing count raises ``CountValidationError`` ("counts must come from
    data, not be invented"), not a bare ``KeyError``.
  * Exclusion side-box ``(n = …)`` numbers are derived from the cascade's ``excluded`` value
    for that step (``FlowNode.excluded``), not hardcoded literals, so the number shown is the
    number ``validate_cascade`` reconciled (parent = child + excluded). The bullet-list
    *reasons* remain overridable illustrative placeholders.

No copyrighted checklist text is reproduced — only the node skeleton/layout (a fact).
Exclusion reasons are illustrative placeholders the caller overrides with real study data.
"""

from __future__ import annotations

from collections.abc import Callable

from ..models import Edge, Entity, EntityKind, FigureSchema, FigureType
from .counts import Cascade, CountValidationError, FlowNode, derive_counts, fill_template

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


def _resolve_counts(
    cascade: Cascade, counts: dict[str, int] | None
) -> dict[str, int]:
    """Populate the cascade's box counts (from ``counts`` if given, else the exemplar), then
    validate the cascade and return the box-key -> count mapping.

    This is the ONE validated code path shared by the exemplar (``counts is None``) and the
    caller branches: ``derive_counts`` (hence ``validate_cascade``) runs in both. A caller
    dict whose arithmetic doesn't reconcile raises ``CountValidationError`` here, before any
    label is filled — the count is never rendered raw.

    When a caller supplies its own ``counts``, it must supply EVERY box count (strict
    completeness — a partial dict raises ``CountValidationError`` rather than rendering the
    caller's real numbers mixed with leftover exemplar numbers). Each waterfall step's
    ``excluded`` is then re-derived from the data as ``parent − child`` so the side-box number
    reflects the caller's cascade (H1) rather than a stale exemplar literal; the derivation law
    (``child == parent − excluded``) and the non-negativity guard then hold against the real
    numbers, while the split law (a branch node's count equals the sum of its arms, e.g. ``rand
    == alloc_tx + alloc_ctrl``) is the cross-arm reconciliation that catches an inconsistent
    dict (the C1 defect). When ``counts is None`` the same validated path runs on the worked
    exemplar.
    """
    if counts is not None:
        nodes = cascade.nodes
        # Strict completeness (H2): a partial caller dict is a data error. If the caller
        # supplies its own counts, every box count must come from that data — silently mixing
        # the caller's real numbers with leftover exemplar numbers for un-supplied boxes would
        # render invented counts. Surface the missing boxes as CountValidationError (the
        # "counts must come from data, not be invented" guard), never a bare KeyError, and never
        # a half-real figure.
        missing = [key for key in nodes if key not in counts]
        if missing:
            raise CountValidationError(
                [f"no source count for box '{k}' (counts must come from data, "
                 f"not be invented)" for k in missing]
            )
        for key, node in nodes.items():
            node.count = counts[key]
        # Re-derive each waterfall step's excluded from the (now caller-populated) counts, so
        # the side-box number is parent − child (data-driven, H1). A child that exceeds its
        # parent yields a negative excluded, which validate_cascade rejects.
        for node in nodes.values():
            if node.derive_from is not None and node.derive_from in nodes:
                node.excluded = nodes[node.derive_from].count - node.count
    return derive_counts(cascade)


def _excluded_for(cascade: Cascade, key: str) -> int:
    """The number excluded at the step that DERIVES ``key`` — the reconciled side-box count."""
    return cascade.nodes[key].excluded


# --------------------------------------------------------------------------- #
# STROBE — observational cohort flow
# --------------------------------------------------------------------------- #
def build_strobe(counts: dict[str, int] | None = None) -> FigureSchema:
    """STROBE cohort-study participant-flow skeleton (source -> dedup -> eligible -> cohort
    -> exposed/unexposed -> outcomes), with two exclusion side-boxes."""
    cascade = Cascade(
        {
            "source": FlowNode("source", 120000),
            "unique": FlowNode("unique", 85000),
            "eligible": FlowNode("eligible", 80000, derive_from="unique", excluded=5000),
            "cohort": FlowNode(
                "cohort", 77500, derive_from="eligible", excluded=2500,
                split=["exp", "unexp"],
            ),
            "exp": FlowNode("exp", 20000),
            "unexp": FlowNode("unexp", 57500),
        }
    )
    c = _resolve_counts(cascade, counts)
    e = [
        _spine("source", fill_template("Source population\n(records = {source})", c)),
        _spine("unique", fill_template("Unique subjects after deduplication\nN = {unique}", c)),
        _side(
            "excl1",
            fill_template(
                "Excluded (n = {_excl_eligible}):\n• Missing age/sex\n• Outside age range",
                {**c, "_excl_eligible": _excluded_for(cascade, "eligible")},
            ),
            beside="unique",
        ),
        _spine("eligible", fill_template("Meeting eligibility criteria\nN = {eligible}", c)),
        _side(
            "excl2",
            fill_template(
                "Excluded (n = {_excl_cohort}):\n• Prior event at baseline\n"
                "• Follow-up ≤ 0 days",
                {**c, "_excl_cohort": _excluded_for(cascade, "cohort")},
            ),
            beside="eligible",
        ),
        _spine("cohort", fill_template("Analytic cohort\nN = {cohort}", c), highlight=True),
        _spine("exp", fill_template("Exposed\nn = {exp}", c), group="exposed"),
        _spine("unexp", fill_template("Unexposed\nn = {unexp}", c), group="unexposed"),
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
    cascade = Cascade(
        {
            "assessed": FlowNode("assessed", 500),
            "rand": FlowNode(
                "rand", 400, derive_from="assessed", excluded=100,
                split=["alloc_tx", "alloc_ctrl"],
            ),
            "alloc_tx": FlowNode("alloc_tx", 200),
            "alloc_ctrl": FlowNode("alloc_ctrl", 200),
        }
    )
    c = _resolve_counts(cascade, counts)
    e = [
        _spine("assessed", fill_template("Assessed for eligibility\n(n = {assessed})", c)),
        _side(
            "excl",
            fill_template(
                "Excluded (n = {_excl_rand}):\n• Not meeting inclusion criteria\n"
                "• Declined to participate\n• Other reasons",
                {**c, "_excl_rand": _excluded_for(cascade, "rand")},
            ),
            beside="assessed",
        ),
        _spine("rand", fill_template("Randomized\n(n = {rand})", c), highlight=True),
        _spine(
            "alloc_tx",
            fill_template("Allocated to intervention\n(n = {alloc_tx})", c),
            group="intervention",
        ),
        _spine(
            "alloc_ctrl",
            fill_template("Allocated to control\n(n = {alloc_ctrl})", c),
            group="control",
        ),
        _spine("fu_tx", "Lost to follow-up\nDiscontinued intervention", group="intervention"),
        _spine("fu_ctrl", "Lost to follow-up\nDiscontinued control", group="control"),
        _spine("ana_tx", fill_template("Analyzed\n(n = {alloc_tx})", c), group="intervention"),
        _spine("ana_ctrl", fill_template("Analyzed\n(n = {alloc_ctrl})", c), group="control"),
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
    excluded). The exclusion cascade is the canonical reporting-flow side-box pattern.

    The ``dedup`` ("after duplicates removed") count reconciles with grant-forge's flowfig
    relationship ``dedup = identified + additional − duplicates``: ``flow_count_problems``
    bounds ``dedup`` by the sum of its solid-flow sources (id_db + id_other). Modelling
    ``duplicates`` as a hard cascade ``excluded`` here would require every caller to supply a
    duplicates count, so the deduplication step is left as the inflow-conservation guard
    (the weaker but always-applicable check) and the exemplar's ``dedup`` is taken as given —
    matching what flowfig hands in when it computes the same value upstream.
    """
    cascade = Cascade(
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
    c = _resolve_counts(cascade, counts)
    e = [
        _spine("id_db", fill_template("Records identified from databases\n(n = {id_db})", c)),
        _spine(
            "id_other",
            fill_template("Records identified from other sources\n(n = {id_other})", c),
        ),
        _spine("dedup", fill_template("Records after duplicates removed\n(n = {dedup})", c)),
        _spine(
            "screened",
            fill_template("Records screened (title/abstract)\n(n = {screened})", c),
        ),
        _side(
            "excl_ta",
            fill_template(
                "Records excluded\n(n = {_excl_ft_sought})",
                {**c, "_excl_ft_sought": _excluded_for(cascade, "ft_sought")},
            ),
            beside="screened",
        ),
        _spine("ft_sought", fill_template("Reports sought for retrieval\n(n = {ft_sought})", c)),
        _side(
            "ft_notret",
            fill_template(
                "Reports not retrieved\n(n = {_excl_ft_assessed})",
                {**c, "_excl_ft_assessed": _excluded_for(cascade, "ft_assessed")},
            ),
            beside="ft_sought",
        ),
        _spine(
            "ft_assessed",
            fill_template("Reports assessed for eligibility\n(n = {ft_assessed})", c),
        ),
        _side(
            "ft_excl",
            fill_template(
                "Reports excluded (n = {_excl_included}):\n• Wrong population\n"
                "• Wrong index test\n• Wrong outcome\n• Abstract only\n• Duplicate cohort",
                {**c, "_excl_included": _excluded_for(cascade, "included")},
            ),
            beside="ft_assessed",
        ),
        _spine(
            "included",
            fill_template("Studies included in review\n(n = {included})", c),
            highlight=True,
        ),
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
    cascade = Cascade(
        {
            "eligible": FlowNode("eligible", 500),
            "index": FlowNode("index", 450, derive_from="eligible", excluded=50),
            "ref": FlowNode("ref", 450, split=["idx_pos", "idx_neg"]),
            "idx_pos": FlowNode("idx_pos", 180, split=["tp", "fp"]),
            "idx_neg": FlowNode("idx_neg", 270, split=["fn", "tn"]),
            "tp": FlowNode("tp", 160),
            "fp": FlowNode("fp", 20),
            "fn": FlowNode("fn", 15),
            "tn": FlowNode("tn", 255),
        }
    )
    c = _resolve_counts(cascade, counts)
    e = [
        _spine("eligible", fill_template("Eligible patients\n(n = {eligible})", c)),
        _side(
            "excl",
            fill_template(
                "Excluded (n = {_excl_index}):\n• Contraindication to index test\n"
                "• No reference standard\n• Declined",
                {**c, "_excl_index": _excluded_for(cascade, "index")},
            ),
            beside="eligible",
        ),
        _spine("index", fill_template("Received index test\n(n = {index})", c), highlight=True),
        _spine("ref", fill_template("Received reference standard\n(n = {ref})", c)),
        _spine(
            "idx_pos",
            fill_template("Index test positive\n(n = {idx_pos})", c),
            group="positive",
        ),
        _spine(
            "idx_neg",
            fill_template("Index test negative\n(n = {idx_neg})", c),
            group="negative",
        ),
        _spine("tp", fill_template("Reference positive\nTP = {tp}", c), group="positive"),
        _spine("fp", fill_template("Reference negative\nFP = {fp}", c), group="positive"),
        _spine("fn", fill_template("Reference positive\nFN = {fn}", c), group="negative"),
        _spine("tn", fill_template("Reference negative\nTN = {tn}", c), group="negative"),
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
