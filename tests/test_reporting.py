"""Reporting-guideline flow diagrams: skeletons render compliant, side-box semantics emit the
right dot attributes, and box counts are derived/validated from source (never invented).

Mirrors tests/test_generators.py conventions (route -> generate -> enforce; _texts helper).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from lxml import etree

from scidraw_agent.compose import compose_figure
from scidraw_agent.models import Edge, Entity, FigureSchema, FigureType
from scidraw_agent.palette import PaletteRegistry
from scidraw_agent.reporting import (
    GUIDELINES,
    build_consort,
    build_guideline_flow,
    build_prisma,
    build_stard,
    build_strobe,
)
from scidraw_agent.reporting.counts import (
    Cascade,
    CountValidationError,
    FlowNode,
    derive_counts,
    extract_counts,
    fill_template,
    validate_cascade,
)
from scidraw_agent.router import route
from scidraw_agent.selfcheck import flow_count_problems, self_check
from scidraw_agent.standards import enforce
from scidraw_agent.theme import StyleSpec, cohen_lab

SVG = "http://www.w3.org/2000/svg"
FIXTURES = Path(__file__).parent / "fixtures" / "reporting"
HAVE_DOT = shutil.which("dot") is not None
needs_dot = pytest.mark.skipif(not HAVE_DOT, reason="system graphviz `dot` not installed")


def _texts(svg: str) -> list[str]:
    root = etree.fromstring(svg.encode())
    return [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]


def _dot_source(schema: FigureSchema, style: StyleSpec | None = None) -> str:
    """The Graphviz dot source for a schema (layout layer; no rendering / no `dot` needed)."""
    style = style or StyleSpec()
    gen = route(schema.figure_type)
    return gen.build_dot(schema, style, PaletteRegistry(colors=list(style.categorical))).source


# --------------------------------------------------------------------------- #
# Routing + the four skeletons as valid schemas
# --------------------------------------------------------------------------- #
def test_reporting_flow_routes_to_pipeline_generator():
    assert route(FigureType.REPORTING_FLOW).__class__.__name__ == "PipelineGenerator"


@pytest.mark.parametrize("name", sorted(GUIDELINES))
def test_skeleton_is_a_valid_figure_schema(name):
    schema = build_guideline_flow(name)
    assert schema.figure_type is FigureType.REPORTING_FLOW
    assert schema.entities and schema.edges
    # every edge endpoint is a declared entity (no dangling references)
    assert schema.dangling_edges() == []
    # round-trips through the IR
    restored = FigureSchema.model_validate(json.loads(schema.model_dump_json()))
    assert restored == schema


@pytest.mark.parametrize("name", sorted(GUIDELINES))
def test_skeleton_matches_golden_fixture(name):
    """The four template outputs are pinned as goldens; a structural change must update them."""
    golden = json.loads((FIXTURES / f"{name}_flow.json").read_text())
    built = json.loads(build_guideline_flow(name).model_dump_json())
    assert built == golden


# --------------------------------------------------------------------------- #
# Rendering + standards engine
# --------------------------------------------------------------------------- #
@needs_dot
@pytest.mark.parametrize("name", sorted(GUIDELINES))
def test_skeleton_renders_to_valid_svg_and_passes_standards(name):
    schema = build_guideline_flow(name)
    style = cohen_lab()
    palette = PaletteRegistry(colors=list(style.categorical))
    result = route(schema.figure_type).generate(schema, style, palette)
    # enforce must NOT raise (no BLOCK violation) and must return parseable SVG
    cleaned, report = enforce(result.svg, style, data_kind=schema.data_kind)
    root = etree.fromstring(cleaned.encode())
    assert root.tag.endswith("svg")
    # box labels are kept as text (vector-native, editable); the exclusion side-box survives
    texts = " ".join(_texts(cleaned))
    assert "exclud" in texts.lower()
    # graphviz white background polygon was stripped by the guard
    bg = [
        p for p in root.findall(f".//{{{SVG}}}polygon")
        if (p.get("fill") or "").lower() in ("white", "#ffffff")
    ]
    assert bg == []


@needs_dot
def test_prisma_includes_phase_labels_as_text():
    cleaned, _ = enforce(
        route(FigureType.REPORTING_FLOW)
        .generate(build_prisma(), StyleSpec(), PaletteRegistry())
        .svg,
        StyleSpec(),
    )
    texts = " ".join(_texts(cleaned))
    for needle in ("identified", "screened", "eligibility", "included"):
        assert needle in texts.lower()


# --------------------------------------------------------------------------- #
# Exclusion-cascade side-box dot semantics (asserted at the dot layer — no `dot` needed)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", sorted(GUIDELINES))
def test_side_boxes_emit_dashed_arrowless_nonconstraining_rank_same(name):
    schema = build_guideline_flow(name)
    n_side = sum(1 for e in schema.entities if e.side_box)
    assert n_side >= 1  # every guideline flow has at least one exclusion side-box
    dot = _dot_source(schema)
    # one dashed + arrowless + rank=same + note-shaped side-box per exclusion box
    assert dot.count("style=dashed") == n_side
    assert dot.count("dir=none") == n_side
    assert dot.count("rank=same") == n_side
    assert dot.count("shape=note") == n_side
    # constraint=false on at least every exclusion edge (PRISMA also has the off-spine merge)
    assert dot.count("constraint=false") >= n_side


def test_side_box_attributes_are_general_not_prisma_hardcoded():
    """A hand-built flow with the schema flags emits the same dot semantics — the cascade is a
    general schema feature, not wired to any specific guideline."""
    schema = FigureSchema(
        figure_type=FigureType.REPORTING_FLOW,
        entities=[
            Entity(id="a", label="Enrolled\n(n = 100)"),
            Entity(id="b", label="Analyzed\n(n = 90)"),
            Entity(id="x", label="Excluded\n(n = 10)", side_box=True, rank_with="a"),
        ],
        edges=[
            Edge(source="a", target="b", relation="flows_to"),
            Edge(source="a", target="x", relation="other",
                 style="dashed", arrow=False, constraint=False),
        ],
    )
    dot = _dot_source(schema)
    assert "style=dashed" in dot and "dir=none" in dot
    assert "constraint=false" in dot and "rank=same" in dot
    assert "shape=note" in dot


@needs_dot
def test_dashed_exclusion_edge_survives_to_svg():
    cleaned, _ = enforce(
        route(FigureType.REPORTING_FLOW)
        .generate(build_consort(), StyleSpec(), PaletteRegistry())
        .svg,
        StyleSpec(),
    )
    assert "stroke-dasharray" in cleaned  # the dashed side branch reaches the SVG


# --------------------------------------------------------------------------- #
# Count derivation — counts come from source data, not invented
# --------------------------------------------------------------------------- #
def test_extract_counts_reads_flow_notation():
    assert extract_counts("Eligible n = 500\nTP = 160, FP = 20") == [500, 160, 20]
    assert extract_counts("Records (n = 3,500)") == [3500]  # thousands separator


def test_fill_template_uses_source_counts():
    out = fill_template("Analytic cohort\nN = {n_cohort}", {"n_cohort": 1284})
    assert "1,284" in out  # publication thousands separator


def test_fill_template_refuses_to_invent_a_missing_count():
    # TEETH: a placeholder with no source count must raise, never guess a number.
    with pytest.raises(CountValidationError):
        fill_template("Cohort N = {n_cohort}", {})


def test_validate_cascade_accepts_consistent_arithmetic():
    cascade = Cascade(
        {
            "assessed": FlowNode("assessed", 500),
            "rand": FlowNode("rand", 400, derive_from="assessed", excluded=100),
            "tx": FlowNode("tx", 200),
            "ctrl": FlowNode("ctrl", 200),
            "_arms": FlowNode("_arms", 400, split=["tx", "ctrl"]),
        }
    )
    validate_cascade(cascade)  # must not raise
    assert derive_counts(cascade)["rand"] == 400


def test_validate_cascade_flags_derivation_mismatch():
    # TEETH: rand should be assessed - excluded = 390, not 400.
    cascade = Cascade(
        {
            "assessed": FlowNode("assessed", 500),
            "rand": FlowNode("rand", 400, derive_from="assessed", excluded=110),
        }
    )
    with pytest.raises(CountValidationError) as ei:
        validate_cascade(cascade)
    assert "rand" in str(ei.value)


def test_validate_cascade_flags_split_sum_mismatch():
    # TEETH: the split node carries 400 but its children sum to 410 (arms don't add up).
    cascade = Cascade(
        {
            "tx": FlowNode("tx", 210),
            "ctrl": FlowNode("ctrl", 200),
            "rand": FlowNode("rand", 400, split=["tx", "ctrl"]),
        }
    )
    with pytest.raises(CountValidationError):
        validate_cascade(cascade)


# --------------------------------------------------------------------------- #
# Self-check wiring — flow_count_problems is clean on valid, fires on invented
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", sorted(GUIDELINES))
def test_valid_skeleton_has_no_flow_count_problems(name):
    assert flow_count_problems(build_guideline_flow(name)) == []


def test_flow_count_problem_on_invented_split_child():
    # TEETH: inflate a 2x2 cell above what flows into it; the guard must flag it. If the
    # "counts cannot grow down the flow" check were removed, this assertion fails.
    schema = build_stard()
    for e in schema.entities:
        if e.id == "idx_pos":
            e.label = "Index test positive\n(n = 9999)"
    problems = flow_count_problems(schema)
    assert problems and "9999" in problems[0]


def test_flow_count_problem_on_invented_terminal_count():
    schema = build_prisma()
    for e in schema.entities:
        if e.id == "included":
            e.label = "Studies included in review\n(n = 9999)"
    problems = flow_count_problems(schema)
    assert any("9999" in p for p in problems)


def test_self_check_surfaces_flow_count_problem():
    schema = build_consort()
    for e in schema.entities:
        if e.id == "alloc_tx":
            e.label = "Allocated to intervention\n(n = 9999)"
    # self_check aggregates flow_count_problems alongside invented-entity / dangling-edge checks
    warnings = self_check("rct consort allocated randomized analyzed", schema)
    assert any("9999" in w for w in warnings)


# --------------------------------------------------------------------------- #
# Counts flow through to the rendered boxes
# --------------------------------------------------------------------------- #
def test_explicit_counts_fill_the_boxes():
    counts = {
        "assessed": 800, "rand": 600, "alloc_tx": 300, "alloc_ctrl": 300,
    }
    schema = build_consort(counts)
    labels = " ".join(e.label for e in schema.entities)
    assert "800" in labels and "600" in labels and "300" in labels
    # the supplied counts are internally consistent, so the self-check stays clean
    assert flow_count_problems(schema) == []


# --------------------------------------------------------------------------- #
# Caller-supplied counts go through the SAME validated path as the exemplar.
# These are the regression guards for the reporting-flow count-derivation
# defects (C1/H1/H2/C2): a caller dict must be reconciled, not rendered raw.
# --------------------------------------------------------------------------- #
def test_caller_counts_inconsistent_arms_raise_count_validation_error():
    # C1: build_consort with arms that do NOT sum to the randomized total must
    # raise (validate_cascade has to run on the caller branch, not only the
    # counts-is-None exemplar branch). alloc_tx + alloc_ctrl = 1000 != rand 600.
    with pytest.raises(CountValidationError):
        build_consort(
            {"assessed": 800, "rand": 600, "alloc_tx": 999, "alloc_ctrl": 1}
        )


def test_caller_counts_inconsistent_derivation_raise():
    # C1: derivation law — rand must equal assessed - excluded. Here the spine
    # 800 -> 600 implies 200 excluded; arms are consistent (300+300=600) but the
    # build must still reconcile the cascade. An assessed/rand pair that cannot
    # reconcile (e.g. arms summing to the wrong total) surfaces as an error.
    with pytest.raises(CountValidationError):
        build_consort(
            {"assessed": 800, "rand": 600, "alloc_tx": 400, "alloc_ctrl": 400}
        )


def test_caller_counts_side_box_number_derived_from_data():
    # H1: the exclusion side-box (n = …) must be DERIVED from the cascade's
    # excluded value (parent - child), not a hardcoded literal. Spine 800 -> 750
    # means 50 excluded; the side box must read 50, never the exemplar's 100.
    schema = build_consort(
        {"assessed": 800, "rand": 750, "alloc_tx": 375, "alloc_ctrl": 375}
    )
    side = next(e for e in schema.entities if e.id == "excl")
    excluded = extract_counts(side.label)
    assert excluded and excluded[0] == 50  # 800 - 750, NOT the literal 100
    # and the spine boxes show the caller numbers
    labels = " ".join(e.label for e in schema.entities)
    assert "800" in labels and "750" in labels
    # internally consistent -> self-check clean
    assert flow_count_problems(schema) == []


def test_strobe_side_box_numbers_derived_from_data():
    # H1 (second guideline): STROBE has two exclusion side-boxes; both numbers
    # must track the caller's cascade, not the 5,000 / 2,500 exemplar literals.
    schema = build_strobe(
        {
            "source": 1000,
            "unique": 900,
            "eligible": 850,
            "cohort": 800,
            "exp": 300,
            "unexp": 500,
        }
    )
    excl1 = next(e for e in schema.entities if e.id == "excl1")
    excl2 = next(e for e in schema.entities if e.id == "excl2")
    assert extract_counts(excl1.label)[0] == 50   # unique 900 -> eligible 850
    assert extract_counts(excl2.label)[0] == 50   # eligible 850 -> cohort 800
    assert flow_count_problems(schema) == []


def test_caller_counts_missing_key_raises_count_validation_not_keyerror():
    # H2: a partial caller dict must raise CountValidationError (the
    # "counts must come from data, not be invented" guard), NOT a bare KeyError.
    with pytest.raises(CountValidationError):
        build_consort({"assessed": 800})


def test_compose_figure_surfaces_flow_count_warning_for_reporting_flow(tmp_path):
    # C2: an externally-authored reporting_flow schema rendered through
    # compose_figure (the compose-schema render path) must have the
    # flow-count self-check run and its findings land in the manifest warnings.
    # Inflate the terminal box above its inflow.
    schema = build_prisma()
    for e in schema.entities:
        if e.id == "included":
            e.label = "Studies included in review\n(n = 9999)"
    manifest = compose_figure(schema, tmp_path, export_png=False)
    assert any("9999" in w for w in manifest.warnings)
