"""Self-check: catch invented / omitted entities and undeclared brain orientation.

The agent must not invent anatomy or steps the source text does not support, and any brain
slice must declare its orientation (neurological/radiological) with L/R markers.
"""

from __future__ import annotations

import re

from .models import FigureSchema
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


def self_check(prompt: str, schema: FigureSchema) -> list[str]:
    """Aggregate non-fatal self-check warnings for the manifest."""
    warnings = []
    for label in invented_entities(prompt, schema):
        warnings.append(f"possible invented entity not grounded in prompt: '{label}'")
    for label in brain_panels_missing_orientation(schema):
        warnings.append(f"brain slice '{label}' lacks orientation/L-R declaration")
    for edge in schema.dangling_edges():
        warnings.append(f"edge references unknown entity: {edge.source}->{edge.target}")
    return warnings
