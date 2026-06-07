"""M0: data-contract round-trips and validation aids."""

from __future__ import annotations

import json

from scidraw_agent.models import (
    AssetRecord,
    DataKind,
    Edge,
    EdgeRelation,
    Entity,
    EntityKind,
    FigureSchema,
    FigureType,
    Manifest,
    StandardsAction,
    StandardsReport,
    StandardsTier,
)


def _sample_schema() -> FigureSchema:
    return FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[
            Entity(id="m1", label="M1", kind=EntityKind.REGION, suggested_asset_query="cortex"),
            Entity(id="sc", label="Spinal cord", kind=EntityKind.REGION),
        ],
        edges=[Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO, label="CST")],
        data_kind=DataKind.NONE,
        caption_seed="Corticospinal projection from M1 to spinal cord.",
    )


def test_figure_schema_roundtrip():
    schema = _sample_schema()
    restored = FigureSchema.model_validate(json.loads(schema.model_dump_json()))
    assert restored == schema
    assert restored.figure_type is FigureType.MECHANISTIC_CIRCUIT
    assert restored.edges[0].relation is EdgeRelation.PROJECTS_TO


def test_entity_ids_and_dangling_edges():
    schema = _sample_schema()
    assert schema.entity_ids() == {"m1", "sc"}
    assert schema.dangling_edges() == []

    schema.edges.append(Edge(source="m1", target="ghost", relation=EdgeRelation.EXCITES))
    dangling = schema.dangling_edges()
    assert len(dangling) == 1 and dangling[0].target == "ghost"


def test_standards_report_routing():
    report = StandardsReport()
    report.add(
        StandardsAction(
            rule_id="no_pie", tier=StandardsTier.BLOCK, message="pie->bar", auto_fixed=True
        )
    )
    report.add(StandardsAction(rule_id="ticks", tier=StandardsTier.WARN, message="too many ticks"))
    report.add(
        StandardsAction(
            rule_id="no_red_green", tier=StandardsTier.BLOCK, message="override honoured"
        )
    )
    assert len(report.applied_fixes) == 1
    assert len(report.warnings) == 1
    assert len(report.overrides) == 1  # block, not auto-fixed -> treated as honoured override


def test_manifest_roundtrip_with_assets_and_standards():
    manifest = Manifest(
        figure_type=FigureType.ANATOMICAL,
        caption_seed="seed",
        assets=[
            AssetRecord(
                query="pyramidal neuron",
                title="Pyramidal neuron",
                backend="zenodo",
                doi="10.5281/zenodo.3925927",
                license="cc-by-4.0",
            )
        ],
    )
    manifest.standards.add(
        StandardsAction(
            rule_id="spines", tier=StandardsTier.DEFAULT, message="hid top/right", auto_fixed=True
        )
    )
    restored = Manifest.model_validate(json.loads(manifest.model_dump_json()))
    assert restored.assets[0].license == "cc-by-4.0"
    assert restored.standards.applied_fixes[0].rule_id == "spines"


def test_default_config_importable():
    from scidraw_agent.config import load_config

    cfg = load_config()
    assert cfg.model  # default model present
    assert cfg.user_agent.startswith("scidraw-agent/")
