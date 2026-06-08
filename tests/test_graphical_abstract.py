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
