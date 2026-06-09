"""Structural graphical-abstract generator: layout, image slots, credits."""

from __future__ import annotations

import json

from lxml import etree

from scidraw_agent.compose import compose_graphical_abstract
from scidraw_agent.config import Config
from scidraw_agent.generators.graphical_abstract import build_graphical_abstract_svg
from scidraw_agent.models import (
    GAImage,
    GAItem,
    GARow,
    GASection,
    GAStep,
    GraphicalAbstract,
)
from scidraw_agent.theme import StyleSpec, cohen_lab

SVG = "http://www.w3.org/2000/svg"


def _ga():
    return GraphicalAbstract(
        title="Test Abstract",
        sections=[
            GASection(
                title="A · Inputs",
                connector="arrow",
                items=[
                    GAItem(title="Cohort", lines=["n=125", "labels"]),
                    GAItem(title="Pipeline", image=GAImage(caption="render here")),  # unfilled
                ],
            ),
            GASection(
                title="B · Analysis",
                items=[
                    GAItem(
                        kind="track",
                        title="Track 1",
                        steps=[GAStep(head="Step one", detail="do a thing")],
                    )
                ],
            ),
            GASection(
                title="C · Outcomes",
                connector="plus",
                items=[GAItem(title="Biomarker"), GAItem(title="Target")],
            ),
        ],
    )


def _texts(svg):
    root = etree.fromstring(svg.encode())
    return [t.text for t in root.findall(f".//{{{SVG}}}text") if t.text]


def test_build_lays_out_sections_cards_tracks_text_as_text():
    svg, assets, warnings = build_graphical_abstract_svg(_ga(), cohen_lab(), fetcher=None)
    texts = _texts(svg)
    assert "Test Abstract" in texts
    assert {"A · Inputs", "B · Analysis", "C · Outcomes"} <= set(texts)
    assert "Cohort" in texts and "Track 1" in texts and "Step one" in texts
    assert "1" in texts  # numbered step badge
    assert "+" in texts  # outcome connector
    # unfilled image slot -> placeholder + warning (recorded for honesty)
    assert any("slot" in t for t in texts)
    assert any("unfilled" in w for w in warnings)


def test_image_slot_prefers_local_render_path(tmp_path):
    asset = tmp_path / "render.svg"
    asset.write_text(f'<svg xmlns="{SVG}" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>')
    ga = GraphicalAbstract(
        sections=[
            GASection(
                title="A",
                items=[GAItem(title="Brain", image=GAImage(path=str(asset), caption="my render"))],
            )
        ]
    )
    svg, assets, warnings = build_graphical_abstract_svg(ga, StyleSpec(), fetcher=None)
    assert "<circle" in svg  # the local render was embedded inline
    assert warnings == []  # no placeholder
    assert assets == []  # the user's own render needs no licence/attribution


def test_compose_writes_svg_credits_and_records_placeholder(tmp_path):
    cfg = Config(cache_dir=tmp_path / "cache")
    out = tmp_path / "out"
    manifest = compose_graphical_abstract(_ga(), out, config=cfg, style=cohen_lab(), fetcher=None)
    assert (out / "figure.svg").exists()
    assert (out / "figure.credits.txt").exists()
    data = json.loads((out / "figure.manifest.json").read_text())
    assert "credits" in data
    # the unfilled slot is recorded as a placeholder asset + warning
    assert any(a.is_placeholder for a in manifest.assets)
    assert any("unfilled" in w for w in manifest.warnings)


def test_multirow_section_stacks_rows():
    ga = GraphicalAbstract(
        sections=[
            GASection(
                title="A",
                rows=[
                    GARow(items=[GAItem(title="r1c1"), GAItem(title="r1c2")]),
                    GARow(connector="arrow", items=[GAItem(title="r2c1")]),
                ],
            )
        ]
    )
    svg, _, _ = build_graphical_abstract_svg(ga, cohen_lab(), fetcher=None)
    assert {"r1c1", "r1c2", "r2c1"} <= set(_texts(svg))


def test_section_as_rows_backward_compat():
    # legacy items+connector still yields one row
    sec = GASection(title="A", items=[GAItem(title="x")], connector="plus")
    rows = sec.as_rows()
    assert len(rows) == 1 and rows[0].connector == "plus" and rows[0].items[0].title == "x"


def test_image_grid_draws_all_cells():
    ga = GraphicalAbstract(
        sections=[
            GASection(
                title="A",
                items=[
                    GAItem(
                        kind="grid",
                        title="Montage",
                        images=[GAImage(caption=f"c{i}") for i in range(4)],
                    )
                ],
            )
        ]
    )
    svg, _, warnings = build_graphical_abstract_svg(ga, StyleSpec(), fetcher=None)
    assert sum("slot" in (t or "") for t in _texts(svg)) == 4  # 4 placeholder cells
    assert len([w for w in warnings if "unfilled" in w]) == 4


def test_column_width_and_reflow():
    from scidraw_agent.generators.graphical_abstract import COLUMN_PX

    def dims(col):
        ga = GraphicalAbstract(
            column=col,
            sections=[
                GASection(
                    title="Out",
                    connector="plus",
                    items=[GAItem(title="A"), GAItem(title="B"), GAItem(title="C")],
                )
            ],
        )
        root = etree.fromstring(build_graphical_abstract_svg(ga, cohen_lab(), None)[0].encode())
        return float(root.get("width")), float(root.get("height"))

    fw, fh = dims("full")
    tw, th = dims("third")
    assert fw == COLUMN_PX["full"] and tw == COLUMN_PX["third"]  # column widths honoured
    assert th > fh  # third-column reflows the 3 cards from one row to a vertical stack


def test_image_height_override_grows_the_slot():
    from scidraw_agent.generators.graphical_abstract import _img_h

    tall = GAItem(kind="image", image=GAImage(caption="panel", height=260))
    default = GAItem(kind="image", image=GAImage(caption="panel"))
    assert _img_h(tall) == 260
    assert _img_h(default) == 96  # backward-compatible default
    # a taller slot makes the whole abstract taller (legible data panels, not thumbnails)
    def height(item):
        ga = GraphicalAbstract(sections=[GASection(title="A", items=[item])])
        root = etree.fromstring(build_graphical_abstract_svg(ga, cohen_lab(), None)[0].encode())
        return float(root.get("height"))

    assert height(tall) > height(default) + 100


def test_card_icon_recoloured_and_missing_icon_warns():
    # no fetcher -> icon can't resolve -> graceful warning, no crash
    ga = GraphicalAbstract(
        sections=[GASection(title="C", items=[GAItem(title="Outcome", icon="brain")])]
    )
    svg, _, warnings = build_graphical_abstract_svg(ga, cohen_lab(), fetcher=None)
    assert "Outcome" in _texts(svg)
    assert any("icon not found" in w for w in warnings)
