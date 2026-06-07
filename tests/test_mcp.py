"""M6: MCP tools via an in-process FastMCP client (A5)."""

from __future__ import annotations

import asyncio

from fastmcp import Client

from scidraw_agent.mcp_server import mcp
from scidraw_agent.models import Edge, EdgeRelation, Entity, FigureSchema, FigureType


def _call(tool: str, args: dict):
    async def go():
        async with Client(mcp) as client:
            res = await client.call_tool(tool, args)
            return res.data

    return asyncio.run(go())


def test_schema_from_text_declines_neuro_render():
    data = _call("schema_from_text", {"text": "render the lesion t-map on the cortical surface"})
    assert data["declined"] is True
    assert "Surf Ice" in data["reason"]


def test_lint_figure_reports_fixes():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40" viewBox="0 0 60 40">'
        '<defs><filter id="s"><feDropShadow dx="1" dy="1"/></filter></defs>'
        '<rect x="5" y="5" width="20" height="10" fill="#FF0000" filter="url(#s)"/></svg>'
    )
    data = _call("lint_figure", {"svg": svg})
    ids = [a["rule_id"] for a in data["report"]["applied_fixes"]]
    assert "no_shadows" in ids and "no_raw_rgb" in ids
    assert data["blocked"] == []


def test_lint_figure_blocks_pie():
    wedges = "".join(
        f'<path d="M50,50 L90,50 A40,40 0 0 1 {x},{y} Z" fill="#0072B2"/>'
        for x, y in [(70, 86), (20, 70), (40, 18)]
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
        f'viewBox="0 0 100 100">{wedges}</svg>'
    )
    data = _call("lint_figure", {"svg": svg})
    assert any(a["rule_id"] == "no_pie" for a in data["blocked"])


def test_compose_figure_returns_svg_path(tmp_path):
    schema = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id="m1", label="M1"), Entity(id="sc", label="Spinal cord")],
        edges=[Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO)],
    )
    data = _call(
        "compose_figure", {"schema": schema.model_dump(), "out_dir": str(tmp_path / "out")}
    )
    assert data["svg_path"].endswith("figure.svg")
    assert (tmp_path / "out" / "figure.svg").exists()


def test_list_rules_includes_catalog():
    data = _call("list_rules", {})
    assert "no_pie" in data and data["no_pie"]["tier"] == "block"


def test_check_decline_local():
    assert _call("check_decline", {"text": "render the lesion t-map on the cortical surface"})[
        "declined"
    ]
    assert not _call("check_decline", {"text": "M1 projects to spinal cord"})["declined"]


def test_self_check_local_flags_invented_and_dangling():
    schema = {
        "figure_type": "mechanistic_circuit",
        "entities": [{"id": "a", "label": "Amygdala"}, {"id": "b", "label": "Cerebellum"}],
        "edges": [{"source": "a", "target": "ghost", "relation": "other"}],
    }
    data = _call("self_check", {"schema": schema, "source_text": "only the amygdala is described"})
    assert data["valid"] is True
    blob = " ".join(data["warnings"])
    assert "Cerebellum" in blob and "ghost" in blob


def test_compose_figure_local_no_assets(tmp_path):
    schema = {
        "figure_type": "mechanistic_circuit",
        "entities": [{"id": "m1", "label": "M1"}, {"id": "sc", "label": "Spinal cord"}],
        "edges": [{"source": "m1", "target": "sc", "relation": "projects_to"}],
    }
    data = _call(
        "compose_figure",
        {"schema": schema, "out_dir": str(tmp_path / "out"), "use_assets": False},
    )
    assert data["svg_path"].endswith("figure.svg")
    assert (tmp_path / "out" / "figure.svg").exists()


def test_make_figure_declines_neuro_render(tmp_path):
    data = _call(
        "make_figure",
        {"text": "render the lesion t-map on the cortical surface", "out_dir": str(tmp_path)},
    )
    assert data["declined"] is True
    assert "Surf Ice" in data["reason"]
