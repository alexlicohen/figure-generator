"""Neuro-decline render handoff: kind routing + standards baked into the snippet."""

from __future__ import annotations

from scidraw_agent.models import DataKind
from scidraw_agent.render_handoff import RenderKind, choose_render_kind, render_snippet
from scidraw_agent.theme import StyleSpec


def test_kind_routing():
    assert choose_render_kind("plot a glass brain of the t-map") == RenderKind.GLASS_BRAIN
    assert choose_render_kind("render the tractography streamlines") == RenderKind.TRACTOGRAPHY
    assert choose_render_kind("overlay the z-map on the cortical surface") == RenderKind.SURFACE
    assert choose_render_kind("show the connectome edges") == RenderKind.CONNECTOME
    assert choose_render_kind("voxelwise activation map") == RenderKind.STAT_MAP


def test_signed_map_bakes_vik_and_symmetric_cbar():
    h = render_snippet("glass brain t-map", data_kind=DataKind.SIGNED)
    assert h.tool == "nilearn"
    assert "cm.vik" in h.code
    assert "symmetric_cbar=True" in h.code
    assert "plot_abs=False" in h.code  # keep the sign
    assert "annotate=True" in h.code  # L/R stamped
    assert any("Neurological" in n for n in h.notes)


def test_magnitude_map_uses_batlow_sequential():
    h = render_snippet("voxelwise activation map", data_kind=DataKind.MAGNITUDE)
    assert "cm.batlow" in h.code
    assert "symmetric_cbar=False" in h.code


def test_radiological_note_and_journal_size():
    style = StyleSpec(journal="science")  # 121 mm double col
    h = render_snippet("stat map overlay", style=style, orientation="radiological")
    assert any("Radiological" in n for n in h.notes)
    # 121 mm ≈ 4.76 in — the figure size must appear in the snippet
    assert "4.76" in h.code
    assert "dpi=300" in h.code


def test_tractography_uses_surf_ice():
    h = render_snippet("DTI streamlines render")
    assert h.tool == "Surf Ice"
    assert "import gl" in h.code
    assert "vik" in h.code  # Crameri CLUT requested in Surf Ice too


def test_surface_iterates_hemispheres():
    h = render_snippet("project the z-map onto the inflated surface")
    assert h.kind == RenderKind.SURFACE
    assert "plot_surf_stat_map" in h.code
    assert "left" in h.code and "right" in h.code
