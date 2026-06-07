"""M4: extraction, neuro-decline gate (A8), self-check (A3/A8)."""

from __future__ import annotations

import pytest

from scidraw_agent.extract import NeuroDeclineError, extract, neuro_decline_trigger
from scidraw_agent.models import (
    Edge,
    EdgeRelation,
    Entity,
    FigureSchema,
    FigureType,
)
from scidraw_agent.selfcheck import (
    BrainOrientationError,
    invented_entities,
    require_brain_orientation,
    self_check,
)


# --- neuro decline gate (A8) ------------------------------------------------ #
@pytest.mark.parametrize(
    "prompt",
    [
        "render the patient's lesion t-map on the cortical surface",
        "overlay the activation map on the MNI brain",
        "show the tractography streamlines",
        "plot the voxelwise z-map",
        "load the patient.nii and render it",
    ],
)
def test_decline_triggers(prompt):
    assert neuro_decline_trigger(prompt) is not None
    with pytest.raises(NeuroDeclineError) as exc:
        extract(prompt)
    assert "Surf Ice" in str(exc.value) and "nilearn" in str(exc.value)


@pytest.mark.parametrize(
    "prompt",
    [
        "corticospinal projection from M1 to spinal cord, labeled",
        "lesion network mapping methods: mask, normalise, seed the connectome database",
        "study design: TSC patients vs controls, two arms",
    ],
)
def test_non_decline_prompts_pass_gate(prompt):
    assert neuro_decline_trigger(prompt) is None


# --- extraction with a mocked LLM ------------------------------------------- #
class _FakeLLM:
    def __init__(self, *results):
        self._results = list(results)
        self.calls = 0

    def parse(self, schema, *, system, user, **kw):
        self.calls += 1
        r = self._results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_extract_returns_schema():
    schema = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id="m1", label="M1"), Entity(id="sc", label="Spinal cord")],
        edges=[Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO)],
    )
    llm = _FakeLLM(schema)
    out = extract("M1 projects to spinal cord", llm=llm)
    assert out is schema
    assert llm.calls == 1


def test_extract_repairs_once_on_failure():
    good = FigureSchema(figure_type=FigureType.ANALYSIS_PIPELINE)
    llm = _FakeLLM(RuntimeError("bad json"), good)
    out = extract("a pipeline of steps", llm=llm)
    assert out is good
    assert llm.calls == 2


# --- self-check (A3 / A8) --------------------------------------------------- #
def test_invented_entity_flagged():
    schema = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id="a", label="Amygdala"), Entity(id="b", label="Cerebellum")],
    )
    flagged = invented_entities("Only the amygdala is described here.", schema)
    assert "Cerebellum" in flagged and "Amygdala" not in flagged


def test_self_check_aggregates_warnings():
    schema = FigureSchema(
        figure_type=FigureType.ANATOMICAL,
        entities=[Entity(id="ax", label="Axial slice")],
        edges=[Edge(source="ax", target="ghost", relation=EdgeRelation.OTHER)],
    )
    warns = self_check("an axial slice of the brain", schema)
    assert any("orientation" in w for w in warns)
    assert any("unknown entity" in w for w in warns)


def test_brain_orientation_required():
    bad = FigureSchema(
        figure_type=FigureType.ANATOMICAL,
        entities=[Entity(id="ax", label="Axial slice")],
    )
    with pytest.raises(BrainOrientationError):
        require_brain_orientation(bad)

    ok = FigureSchema(
        figure_type=FigureType.ANATOMICAL,
        entities=[Entity(id="ax", label="Axial slice (neurological, L/R)")],
    )
    require_brain_orientation(ok)  # does not raise
