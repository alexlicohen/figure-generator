"""M5: end-to-end ingest -> extract -> self-check -> compose (A2, A3)."""

from __future__ import annotations

import json
from pathlib import Path

from scidraw_agent.config import Config
from scidraw_agent.models import Edge, EdgeRelation, Entity, FigureSchema, FigureType
from scidraw_agent.run import figure_from_file

FIX = Path(__file__).parent / "fixtures"


class _FakeLLM:
    def __init__(self, schema: FigureSchema):
        self.schema = schema

    def parse(self, schema, *, system, user, **kw):
        return self.schema


def _pipeline_schema() -> FigureSchema:
    steps = [
        Entity(id="s1", label="Lesion mask", group="steps"),
        Entity(id="s2", label="Normalise to MNI152", group="steps"),
        Entity(id="s3", label="Seed connectome", group="steps"),
        Entity(id="s4", label="Threshold network map", group="steps"),
    ]
    edges = [
        Edge(source="s1", target="s2", relation=EdgeRelation.FLOWS_TO),
        Edge(source="s2", target="s3", relation=EdgeRelation.FLOWS_TO),
        Edge(source="s3", target="s4", relation=EdgeRelation.FLOWS_TO),
    ]
    return FigureSchema(figure_type=FigureType.ANALYSIS_PIPELINE, entities=steps, edges=edges)


def _study_schema() -> FigureSchema:
    ents = [
        Entity(id="p", label="TSC patients", group="patients"),
        Entity(id="c", label="Matched controls", group="control"),
        Entity(id="a1", label="Aim 1 seizure outcomes", group="patients"),
        Entity(id="a2", label="Aim 2 mTOR inhibition", group="patients"),
    ]
    return FigureSchema(figure_type=FigureType.STUDY_DESIGN, entities=ents)


def test_lesion_methods_to_ordered_pipeline(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    manifest = figure_from_file(
        FIX / "lesion_methods.txt",
        tmp_path / "out",
        config=cfg,
        llm=_FakeLLM(_pipeline_schema()),
        section="methods",
    )
    assert manifest.figure_type is FigureType.ANALYSIS_PIPELINE
    # ordered steps preserved + no invented-entity warnings (labels grounded in text)
    assert not any("invented" in w for w in manifest.warnings)
    assert (tmp_path / "out" / "figure.svg").exists()
    data = json.loads((tmp_path / "out" / "figure.manifest.json").read_text())
    assert data["figure_type"] == "analysis_pipeline"


def test_tsc_aim_to_study_design(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    manifest = figure_from_file(
        FIX / "tsc_aim.txt",
        tmp_path / "out",
        config=cfg,
        llm=_FakeLLM(_study_schema()),
        section="aims",
    )
    assert manifest.figure_type is FigureType.STUDY_DESIGN
    assert not any("invented" in w for w in manifest.warnings)
    assert (tmp_path / "out" / "figure.svg").exists()
