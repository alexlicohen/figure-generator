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


def test_shade_ramp_single_hue_light_to_dark():
    from scidraw_agent.palette import hue_deg, parse_color, shade_ramp

    ramp = shade_ramp("#2F5C8A", 5)
    assert len(ramp) == 5
    lums = [
        0.299 * (rgb := parse_color(c))[0] + 0.587 * rgb[1] + 0.114 * rgb[2] for c in ramp
    ]
    assert lums == sorted(lums, reverse=True)  # light -> dark
    hues = [hue_deg(parse_color(c)) for c in ramp]
    assert max(hues) - min(hues) < 12  # one hue, not a rainbow


def test_sequential_pipeline_uses_one_hue_not_rainbow():
    # ungrouped analysis pipeline -> single-hue ramp (steps don't pull distinct categorical hues)
    schema = FigureSchema(
        figure_type=FigureType.ANALYSIS_PIPELINE,
        entities=[Entity(id=f"s{i}", label=f"Step {i}", kind=EntityKind.STEP) for i in range(4)],
        edges=[
            Edge(source=f"s{i}", target=f"s{i + 1}", relation=EdgeRelation.FLOWS_TO)
            for i in range(3)
        ],
    )
    reg = PaletteRegistry()
    route(schema.figure_type).generate(schema, StyleSpec(), reg, fetcher=None)
    # the shared palette is NOT polluted with one entry per step id (the ramp bypasses assign)
    assert not any(k.startswith("s") for k in reg.mapping)


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


def test_circuit_legend_reflects_present_relations():
    # Graphviz rebuild: the appended legend names exactly the relation types used.
    cleaned, _, _ = _guarded(_circuit_schema())  # projects_to + inhibits
    texts = _texts(cleaned)
    assert "CST" in texts  # edge label rendered
    assert any("excitatory" in t for t in texts)
    assert any(t == "inhibitory" for t in texts)
    assert not any("modulatory" in t for t in texts)


def test_circuit_modulatory_is_dashed_and_in_legend():
    schema = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id="a", label="VTA"), Entity(id="b", label="NAc")],
        edges=[Edge(source="a", target="b", relation=EdgeRelation.MODULATES)],
    )
    cleaned, _, _ = _guarded(schema)
    assert any("modulatory" in t for t in _texts(cleaned))
    assert "stroke-dasharray" in cleaned  # dashed modulatory edge/legend sample


def test_circuit_nonadjacent_edge_does_not_need_adjacency():
    # Regression: the old single-row drawer ran M1->cord straight through the interneuron
    # listed between them. Graphviz layout makes entity order irrelevant; just confirm it
    # renders all three nodes + both relations cleanly.
    schema = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[
            Entity(id="m1", label="M1"),
            Entity(id="inh", label="Interneuron"),  # listed BETWEEN source and target
            Entity(id="sc", label="Cord"),
        ],
        edges=[
            Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO),
            Edge(source="inh", target="m1", relation=EdgeRelation.INHIBITS),
        ],
    )
    cleaned, _, _ = _guarded(schema)
    texts = _texts(cleaned)
    assert {"M1", "Interneuron", "Cord"} <= set(texts)
    assert any("excitatory" in t for t in texts) and any(t == "inhibitory" for t in texts)


def test_anatomical_contrast_darkens_pale_grey_only():
    from scidraw_agent.generators.anatomical import _darken_pale_achromatic

    assert _darken_pale_achromatic((211, 211, 211)) == (127, 127, 127)  # pale grey -> darker
    assert _darken_pale_achromatic((183, 187, 182)) is not None  # near-grey -> darkened
    assert _darken_pale_achromatic((187, 224, 227)) is None  # #BBE0E3 light teal -> spared
    assert _darken_pale_achromatic((121, 121, 121)) is None  # already dark -> kept
    assert _darken_pale_achromatic((255, 255, 255)) is None  # white/background -> kept


def test_anatomical_boost_contrast_rewrites_fill():
    from scidraw_agent.generators.anatomical import _boost_contrast

    svg = f'<svg xmlns="{SVG}"><path style="fill:rgb(211,211,211)"/><rect fill="#BBE0E3"/></svg>'
    root = etree.fromstring(svg.encode())
    _boost_contrast(root)
    path, rect = root.findall(f".//{{{SVG}}}path")[0], root.findall(f".//{{{SVG}}}rect")[0]
    assert "211" not in path.get("style")  # pale grey darkened
    assert rect.get("fill") == "#BBE0E3"  # light teal untouched


def test_asset_style_grayscale_desaturates_and_normalizes():
    from scidraw_agent.generators.anatomical import _normalize_asset

    svg = (
        f'<svg xmlns="{SVG}"><rect fill="#BBE0E3"/>'  # light teal (chromatic)
        f'<path style="fill:rgb(211,211,211)"/></svg>'  # pale grey
    )
    root = etree.fromstring(svg.encode())
    _normalize_asset(root, StyleSpec(asset_style="grayscale"))
    rect = root.findall(f".//{{{SVG}}}rect")[0]
    from scidraw_agent.palette import parse_color

    r, g, b = parse_color(rect.get("fill"))
    assert r == g == b  # desaturated to neutral grey


def test_asset_style_tint_uses_house_ink():
    from scidraw_agent.generators.anatomical import _normalize_asset
    from scidraw_agent.palette import parse_color

    svg = f'<svg xmlns="{SVG}"><rect fill="#999999"/><path fill="#222222"/></svg>'
    root = etree.fromstring(svg.encode())
    _normalize_asset(root, StyleSpec(asset_style="tint", asset_tint="#37576B"))
    for tag in ("rect", "path"):
        r, g, b = parse_color(root.findall(f".//{{{SVG}}}{tag}")[0].get("fill"))
        assert b >= r  # slate-blue ink: blue channel never below red


def test_asset_style_native_is_default_and_unchanged():
    from scidraw_agent.generators.anatomical import _normalize_asset
    from scidraw_agent.palette import parse_color

    assert StyleSpec().asset_style == "native"
    svg = f'<svg xmlns="{SVG}"><rect fill="#BBE0E3"/></svg>'  # light teal stays (native)
    root = etree.fromstring(svg.encode())
    _normalize_asset(root, StyleSpec())
    assert parse_color(root.findall(f".//{{{SVG}}}rect")[0].get("fill")) == (187, 224, 227)


def test_cohen_lab_preset_outline_palette_grayscale():
    from scidraw_agent.theme import cohen_lab

    s = cohen_lab()
    assert s.node_style == "outline"
    assert s.categorical[0] == "#2F5C8A" and s.categorical[1] == "#D97A1E"
    assert s.asset_style == "grayscale"


def test_node_style_outline_renders_white_cards_with_palette_outline():
    from scidraw_agent.palette import PaletteRegistry
    from scidraw_agent.theme import cohen_lab

    schema = FigureSchema(
        figure_type=FigureType.STUDY_DESIGN,
        entities=[Entity(id="a", label="Patients", group="patients")],
        edges=[],
    )
    style = cohen_lab()
    result = route(schema.figure_type).generate(
        schema, style, PaletteRegistry(colors=list(style.categorical)), fetcher=None
    )
    svg = result.svg.lower()
    assert "2f5c8a" in svg  # cohen steel-blue used as the node outline
    assert 'fill="#ffffff"' in svg or 'fill="white"' in svg  # white card, not a filled colour


def test_asset_style_normalizes_css_class_fills():
    import re

    from scidraw_agent.generators.anatomical import _normalize_asset
    from scidraw_agent.palette import parse_color

    # DBCLS/Illustrator SVGs hide fills in <style> CSS classes — these must normalize too.
    svg = f'<svg xmlns="{SVG}"><style>.st0{{fill:#ED1C24}}</style><path class="st0"/></svg>'
    root = etree.fromstring(svg.encode())
    _normalize_asset(root, StyleSpec(asset_style="grayscale"))
    css = root.findall(f".//{{{SVG}}}style")[0].text
    assert "ed1c24" not in css.lower()  # red recoloured
    r, g, b = parse_color(re.search(r"fill:(#[0-9A-Fa-f]{6})", css).group(1))
    assert r == g == b  # to neutral grey
