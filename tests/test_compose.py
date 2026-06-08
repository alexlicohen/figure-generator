"""M3: compose end-to-end (A1, A7) — svg + raster + manifest with both blocks."""

from __future__ import annotations

import json

from lxml import etree

from scidraw_agent.compose import compose_figure, compose_panels
from scidraw_agent.config import Config
from scidraw_agent.models import Edge, EdgeRelation, Entity, FigureSchema, FigureType
from scidraw_agent.palette import PaletteRegistry

SVG = "http://www.w3.org/2000/svg"


def _corticospinal() -> FigureSchema:
    return FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[
            Entity(id="m1", label="M1", group="cortex"),
            Entity(id="sc", label="Spinal cord", group="cord"),
        ],
        edges=[Edge(source="m1", target="sc", relation=EdgeRelation.PROJECTS_TO, label="CST")],
        caption_seed="Corticospinal projection from M1 to spinal cord.",
    )


def test_compose_figure_writes_svg_raster_and_manifest(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    out = tmp_path / "out"
    manifest = compose_figure(_corticospinal(), out, config=cfg)

    svg_path = out / "figure.svg"
    assert svg_path.exists()
    assert (out / "figure.png").exists()
    assert (out / "figure.manifest.json").exists()

    # editable + text-as-text
    root = etree.fromstring(svg_path.read_bytes())
    texts = [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]
    assert "M1" in texts

    # manifest carries license + standards blocks
    data = json.loads((out / "figure.manifest.json").read_text())
    assert "assets" in data and "standards" in data and "credits" in data
    assert manifest.caption_seed.startswith("Corticospinal")

    # paste-ready credits file is always written (no assets here -> "nothing to attribute")
    assert (out / "figure.credits.txt").exists()


def test_compose_anatomical_records_placeholder_warnings(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    schema = FigureSchema(
        figure_type=FigureType.ANATOMICAL,
        entities=[Entity(id="x", label="Putamen", suggested_asset_query="putamen")],
    )
    manifest = compose_figure(schema, tmp_path / "out", config=cfg, fetcher=None)
    assert manifest.warnings  # placeholder warning recorded
    assert any(a.is_placeholder for a in manifest.assets)


def test_multipanel_shares_stable_group_mapping(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    reg = PaletteRegistry()
    panel_a = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[Entity(id="a", label="Patients", group="patients")],
    )
    panel_b = FigureSchema(
        figure_type=FigureType.MECHANISTIC_CIRCUIT,
        entities=[
            Entity(id="b", label="Controls", group="control"),
            Entity(id="c", label="Patients", group="patients"),
        ],
    )
    manifest = compose_panels([panel_a, panel_b], tmp_path / "out", config=cfg, palette=reg)

    # one stable colour per group across both panels
    assert "patients" in reg.mapping and "control" in reg.mapping
    assert reg.mapping["control"].color == "#999999"  # baseline grey
    assert (tmp_path / "out" / "figure.svg").exists()
    assert manifest.svg_path
