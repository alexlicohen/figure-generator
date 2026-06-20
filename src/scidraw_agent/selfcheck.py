"""Self-check: catch invented / omitted entities and undeclared brain orientation.

The agent must not invent anatomy or steps the source text does not support, and any brain
slice must declare its orientation (neurological/radiological) with L/R markers.
"""

from __future__ import annotations

import re

from .models import FigureSchema, FigureType
from .standards.linter import RuleId, rule

_STOPWORDS = {
    "the",
    "and",
    "of",
    "to",
    "a",
    "an",
    "in",
    "on",
    "for",
    "with",
    "via",
    "from",
    "left",
    "right",
    "slice",
    "panel",
    "figure",
    "cell",
    "cells",
    "region",
    "regions",
}
_SLICE_WORDS = {"axial", "coronal", "sagittal", "transverse"}
_ORIENT_WORDS = {"neurological", "radiological"}


class BrainOrientationError(Exception):
    """Raised when a brain slice entity lacks a declared orientation + L/R markers."""

    def __init__(self, labels: list[str]) -> None:
        self.labels = labels
        r = rule(RuleId.BRAIN_ORIENTATION)
        super().__init__(
            "Brain slice panels must declare orientation (neurological/radiological) and "
            f"L/R markers: {labels}. ({r.source_url})"
        )


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOPWORDS}


def invented_entities(prompt: str, schema: FigureSchema) -> list[str]:
    """Entity labels whose content words do not appear in the prompt (possible invention)."""
    prompt_tokens = _tokens(prompt)
    flagged = []
    for e in schema.entities:
        words = _tokens(e.label)
        if words and not (words & prompt_tokens):
            flagged.append(e.label)
    return flagged


def omitted_terms(prompt: str, schema: FigureSchema, candidates: list[str]) -> list[str]:
    """Of the caller-supplied salient terms, those not represented by any entity label."""
    covered = " ".join(e.label.lower() for e in schema.entities)
    return [c for c in candidates if c.lower() not in covered]


def brain_panels_missing_orientation(schema: FigureSchema) -> list[str]:
    flagged = []
    for e in schema.entities:
        text = e.label.lower()
        if any(w in text for w in _SLICE_WORDS):
            has_orient = any(w in text for w in _ORIENT_WORDS)
            has_lr = ("l/r" in text) or ("left" in text and "right" in text)
            if not (has_orient and has_lr):
                flagged.append(e.label)
    return flagged


def require_brain_orientation(schema: FigureSchema) -> None:
    flagged = brain_panels_missing_orientation(schema)
    if flagged:
        raise BrainOrientationError(flagged)


def source_word_coverage(prompt: str, schema: FigureSchema) -> float:
    """Fraction of salient source words that appear in the figure's entity labels.

    Adopted from make-figures ``critic_figure.py`` (source-word coverage idea) but computed on
    the SVG-source IR (label text) rather than via OCR — the structural standards engine already
    reads text directly. Low coverage flags a figure that drops content the source supports.
    """
    src = _tokens(prompt)
    if not src:
        return 1.0
    label_tokens = set()
    for e in schema.entities:
        label_tokens |= _tokens(e.label)
    return len(src & label_tokens) / len(src)


def flow_count_problems(schema: FigureSchema) -> list[str]:
    """Reconcile the ``(n=…)`` counts written into a reporting-flow's box labels against the
    flow graph, so a box carrying a number that does not follow from its inputs — an invented
    or stale count — is flagged.

    This is the IR-side wiring of the "never invent counts" guard. It walks the *solid flow
    edges* (not the dashed exclusion side-branches) and checks one structural invariant that
    holds for any participant flow regardless of guideline — **conservation of inflow**:

      * a node's count may not exceed the **sum of its solid-flow predecessors' counts**.

    This covers both topologies correctly: a *split* (one parent -> several children) bounds
    each child by its single parent, and a *merge* (several sources -> one node, e.g. PRISMA's
    database + other-source records -> after-dedup) bounds the merged node by the sum of its
    sources. A node whose count exceeds what can flow into it carries an invented or stale
    count. Returns non-fatal warnings; the strong per-step arithmetic (parent = children +
    excluded) is enforced by ``reporting.counts.validate_cascade`` when a figure is *built*
    from explicit data.
    """
    from .reporting.counts import extract_counts

    if schema.figure_type != FigureType.REPORTING_FLOW:
        return []

    def _box_count(label: str) -> int | None:
        ns = extract_counts(label)
        # the headline count is the first one on the box (e.g. "Allocated (n=200)\n• ...n=195")
        return ns[0] if ns else None

    counts = {e.id: _box_count(e.label) for e in schema.entities}
    side = {e.id for e in schema.entities if getattr(e, "side_box", False)}
    labels = {e.id: e.label.splitlines()[0] for e in schema.entities}

    # Per child, the solid-flow predecessors feeding it (skip dashed/arrowless exclusion
    # connectors and any edge touching a side-box).
    parents: dict[str, list[str]] = {}
    for edge in schema.edges:
        if getattr(edge, "style", "solid") == "dashed" or not getattr(edge, "arrow", True):
            continue
        if edge.target in side or edge.source in side:
            continue
        parents.setdefault(edge.target, []).append(edge.source)

    problems: list[str] = []
    for child, preds in parents.items():
        cc = counts.get(child)
        if cc is None:
            continue
        pred_counts = [(p, counts[p]) for p in preds if counts.get(p) is not None]
        if not pred_counts:
            continue
        inflow = sum(c for _, c in pred_counts)
        if cc > inflow:
            shown = " + ".join(f"{labels.get(p, p)}={c}" for p, c in pred_counts)
            problems.append(
                f"reporting-flow box '{labels.get(child, child)}' (n={cc}) exceeds its total "
                f"inflow {inflow} ({shown}) — counts cannot grow down the flow "
                "(possible invented/stale count)"
            )
    return problems


def self_check(prompt: str, schema: FigureSchema) -> list[str]:
    """Aggregate non-fatal self-check warnings for the manifest."""
    warnings = []
    for label in invented_entities(prompt, schema):
        warnings.append(f"possible invented entity not grounded in prompt: '{label}'")
    for label in brain_panels_missing_orientation(schema):
        warnings.append(f"brain slice '{label}' lacks orientation/L-R declaration")
    for edge in schema.dangling_edges():
        warnings.append(f"edge references unknown entity: {edge.source}->{edge.target}")
    warnings.extend(flow_count_problems(schema))
    return warnings
