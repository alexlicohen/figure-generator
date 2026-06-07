"""M3: each generator emits standards-compliant SVG after the guard pass."""

from __future__ import annotations

from lxml import etree

from scidraw_agent.models import (
    Edge,
    EdgeRelation,
    Entity,
    EntityKind,
    FigureSchema,
    FigureType,
)
from scidraw_agent.palette import OKABE_ITO, PaletteRegistry, is_raw_primary
from scidraw_agent.router import route
from scidraw_agent.standards import enforce
from scidraw_agent.theme import StyleSpec

SVG = "http://www.w3.org/2000/svg"


def _circuit_schema() -> FigureSchema:
    return FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[
            Entity(id="m1", label="M1", kind=EntityKind.REGION),
            Entity(id="sc", label="Spinal cord", kind=EntityKind.REGION),
            Entity(id="in", label="Inhibitory IN", kind=EntityKind.CELLTYPE),
        ],
        edges=[
            Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO, label="CST"),
            Edge(source="in", target="sc", relation=EdgeRelation.INHIBITS),
        ],
        caption_seed="Corticospinal projection.",
    )


def _guarded(schema):
    gen = route(schema.figure_type)
    result = gen.generate(schema, StyleSpec(), PaletteRegistry(), fetcher=None)
    cleaned, report = enforce(result.svg, StyleSpec(), data_kind=schema.data_kind)
    return cleaned, report, result


def _texts(svg):
    root = etree.fromstring(svg.encode())
    return [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]


def _fills(svg):
    root = etree.fromstring(svg.encode())
    out = []
    for el in root.iter():
        f = el.get("fill")
        if f:
            out.append(f)
    return out


def test_router_dispatch():
    assert route(FigureType.MECHANISTIC_CIRCUIT).__class__.__name__ == "CircuitGenerator"
    assert route(FigureType.ANALYSIS_PIPELINE).__class__.__name__ == "PipelineGenerator"
    assert route(FigureType.STUDY_DESIGN).__class__.__name__ == "PipelineGenerator"
    assert route(FigureType.ANATOMICAL).__class__.__name__ == "AnatomicalGenerator"


def test_circuit_compliant_and_text_kept():
    cleaned, _, _ = _guarded(_circuit_schema())
    texts = _texts(cleaned)
    assert "M1" in texts and "Spinal cord" in texts  # labels kept as text
    # no raw primaries survive; node fills are palette colours
    assert not any(is_raw_primary(f) for f in _fills(cleaned))
    palette_colors = set(OKABE_ITO.values()) | {"#333333", "#FFFFFF", "#999999"}
    node_fills = [f for f in _fills(cleaned) if f.startswith("#")]
    assert any(f in palette_colors for f in node_fills)


def test_pipeline_graphviz_frame_removed():
    schema = FigureSchema(
        figure_type=FigureType.ANALYSIS_PIPELINE,
        entities=[
            Entity(id="s1", label="Lesion mask", kind=EntityKind.STEP),
            Entity(id="s2", label="Normalise", kind=EntityKind.STEP),
            Entity(id="s3", label="Network map", kind=EntityKind.STEP),
        ],
        edges=[
            Edge(source="s1", target="s2", relation=EdgeRelation.FLOWS_TO),
            Edge(source="s2", target="s3", relation=EdgeRelation.FLOWS_TO),
        ],
    )
    cleaned, _, _ = _guarded(schema)
    root = etree.fromstring(cleaned.encode())
    # graphviz white background polygon was stripped
    bg = [
        p
        for p in root.findall(f".//{{{SVG}}}polygon")
        if (p.get("fill") or "").lower() in ("white", "#ffffff")
    ]
    assert bg == []
    assert "Lesion mask" in " ".join(_texts(cleaned))


def test_anatomical_placeholder_path_offline():
    schema = FigureSchema(
        figure_type=FigureType.ANATOMICAL,
        entities=[
            Entity(id="ctx", label="Cortex", suggested_asset_query="cortex"),
            Entity(id="thal", label="Thalamus", suggested_asset_query="thalamus"),
        ],
    )
    cleaned, _, result = _guarded(schema)
    assert all(a.is_placeholder for a in result.assets)
    assert result.warnings and "nilearn" in " ".join(result.warnings)
    assert "schematic — not to scale" in " ".join(_texts(cleaned))
