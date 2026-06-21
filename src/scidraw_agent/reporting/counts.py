"""Count derivation + validation for reporting-guideline flow diagrams.

THE INVARIANT: a flow box's ``(n=…)`` count is *derived from the source data and the cascade
arithmetic*, never invented. Two guards enforce it:

  1. ``fill_template`` substitutes ``{key}`` placeholders only with counts present in the
     supplied (source-derived) mapping; a placeholder with no source count raises rather than
     guessing a number. This is the structural analogue of make-figures'
     ``fill_prisma_template.py`` substitution, but *strict* (no silent ``-`` fallback for the
     flow IR — a missing count is a data error, not a cosmetic blank).

  2. ``validate_cascade`` checks the arithmetic constraints between boxes (a parent count must
     equal the sum of its children + the count excluded at that step). A box whose count does
     not follow from its inputs — i.e. an invented or stale count — fails the check.

These are the Python port of make-figures'
``scripts/derive_figure_legend_counts.py`` (count extraction + caption↔SSOT reconciliation)
and the count-fill logic of ``scripts/fill_prisma_template.py`` (Aperivue, MIT). They wire
into the existing "don't invent entities" self-check via ``selfcheck.flow_count_problems``.

Stdlib-only (re), no YAML/pptx dependency — operates on the owned IR.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "n = 1,284", "n=998", "N = 1284", "TP = 160" — the standard flow-box count notation.
# (Ported from derive_figure_legend_counts.N_RE, widened to the TP/FP/FN/TN STARD cells.)
_COUNT_RE = re.compile(r"\b(?:[nN]|TP|FP|FN|TN)\s*=\s*([0-9][0-9,]*)")
# {key}-style placeholders (ported from fill_prisma_template.TOKEN_RE).
_TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class CountValidationError(ValueError):
    """Raised when a flow box's count is not derivable from the source / cascade arithmetic.

    This is the teeth of the "never invent counts" guard: an invented or stale box count, or a
    cascade whose branches do not sum to their parent, raises this rather than rendering a
    figure with numbers that disagree with the data.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def extract_counts(text: str) -> list[int]:
    """Every integer count appearing in ``n = N`` / ``N = N`` / ``TP = N`` notation, in order.

    Port of make-figures ``derive_figure_legend_counts._ints``. Used to reconcile a free-text
    caption / label against the structured cascade (the flow IR is the single source of truth).
    """
    out: list[int] = []
    for m in _COUNT_RE.finditer(text):
        try:
            out.append(int(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def fill_template(label_template: str, counts: dict[str, int]) -> str:
    """Substitute ``{key}`` placeholders in a box label with source-derived counts.

    A placeholder whose key is absent from ``counts`` raises ``CountValidationError`` — the
    count must come from the source data, never be invented to fill the box. Integers are
    rendered with thousands separators (the publication convention, e.g. ``1,284``).
    """
    missing: list[str] = []

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in counts:
            missing.append(key)
            return m.group(0)
        return f"{counts[key]:,}"

    out = _TOKEN_RE.sub(_sub, label_template)
    if missing:
        raise CountValidationError(
            [f"no source count for placeholder '{{{k}}}' (counts must come from data, "
             f"not be invented)" for k in dict.fromkeys(missing)]
        )
    return out


# --------------------------------------------------------------------------- #
# Cascade arithmetic
# --------------------------------------------------------------------------- #
@dataclass
class FlowNode:
    """One box in the count cascade.

    ``count`` is the box's N. ``derive_from`` (a parent key) + ``excluded`` (count removed at
    this step) lets the box be *derived*: ``count == counts[derive_from] - excluded``. ``split``
    lists child keys whose counts must sum to this box's count (a branch point — e.g. randomized
    -> two arms, or index test -> positive/negative). Either relationship (or both) can be set;
    a box with neither is a source/leaf and is taken as given.
    """

    key: str
    count: int
    derive_from: str | None = None
    excluded: int = 0
    split: list[str] = field(default_factory=list)


@dataclass
class Cascade:
    """A set of flow boxes with their arithmetic relationships, keyed by box key."""

    nodes: dict[str, FlowNode]

    def counts(self) -> dict[str, int]:
        return {k: n.count for k, n in self.nodes.items()}


def validate_cascade(cascade: Cascade) -> None:
    """Raise ``CountValidationError`` if any box count is inconsistent with the cascade.

    Two arithmetic laws (both standard reporting-flow invariants):
      * **derivation** — a box with ``derive_from`` must satisfy
        ``count == parent.count - excluded`` (the screening/eligibility waterfall).
      * **split** — a box with ``split`` children must satisfy
        ``count == sum(child.count for child in split)`` (allocation / 2×2 branch points).
    A figure whose boxes obey both laws cannot carry an invented or stale count; one that
    violates either is rejected before rendering.
    """
    problems: list[str] = []
    nodes = cascade.nodes
    for node in nodes.values():
        if node.derive_from is not None:
            parent = nodes.get(node.derive_from)
            if parent is None:
                problems.append(f"box '{node.key}' derives from unknown box '{node.derive_from}'")
            else:
                expected = parent.count - node.excluded
                if node.count != expected:
                    problems.append(
                        f"box '{node.key}' n={node.count} != {parent.key} "
                        f"({parent.count}) - excluded ({node.excluded}) = {expected}"
                    )
                # Non-negativity: a derived box cannot exceed its parent (the excluded count
                # cannot be negative — counts only shrink down a single-parent waterfall).
                if node.excluded < 0:
                    problems.append(
                        f"box '{node.key}' n={node.count} exceeds {parent.key} "
                        f"({parent.count}) — implied excluded is negative ({node.excluded}); "
                        "a count cannot grow down the flow (invented/stale count)"
                    )
        if node.split:
            missing = [c for c in node.split if c not in nodes]
            if missing:
                problems.append(f"box '{node.key}' splits into unknown box(es) {missing}")
            else:
                total = sum(nodes[c].count for c in node.split)
                if total != node.count:
                    problems.append(
                        f"box '{node.key}' n={node.count} != sum of {node.split} = {total}"
                    )
    if problems:
        raise CountValidationError(problems)


def derive_counts(cascade: Cascade) -> dict[str, int]:
    """Validate the cascade and return the box-key -> count mapping for label filling.

    The single entry point a builder uses: it both *checks* the arithmetic (raising on an
    invented/stale count) and hands back the validated counts to substitute into box labels.
    """
    validate_cascade(cascade)
    return cascade.counts()
