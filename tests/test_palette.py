"""M1: colour palette, colormap selection, CVD distance, stable group mapping."""

from __future__ import annotations

from scidraw_agent.models import DataKind
from scidraw_agent.palette import (
    BASELINE_GREY,
    OKABE_ITO,
    PaletteRegistry,
    colormap_for,
    crameri_stops,
    cvd_min_distance,
    is_raw_primary,
    replacement_colormap,
    snap_to_palette,
)


def test_is_raw_primary():
    assert is_raw_primary("#FF0000")
    assert is_raw_primary("red")
    assert is_raw_primary("lime")
    assert not is_raw_primary("#E69F00")  # okabe-ito orange


def test_snap_to_palette_maps_to_okabe_ito():
    snapped = snap_to_palette("#FF0000")
    assert snapped in OKABE_ITO.values()
    assert snapped.lower() != "#ff0000"


def test_colormap_for_by_kind():
    assert colormap_for(DataKind.SIGNED) == "cmc.vik"
    assert colormap_for(DataKind.MAGNITUDE) == "cmc.batlow"
    assert colormap_for(DataKind.CYCLIC) == "cmc.vikO"
    assert colormap_for(DataKind.CATEGORICAL) is None
    assert colormap_for(DataKind.NONE) is None


def test_replacement_colormap_defaults_to_vik():
    assert replacement_colormap(None) == "cmc.vik"
    assert replacement_colormap(DataKind.MAGNITUDE) == "cmc.batlow"


def test_crameri_stops_length_and_hex():
    stops = crameri_stops("cmc.vik", n=5)
    assert len(stops) == 5
    assert all(s.startswith("#") and len(s) == 7 for s in stops)


def test_cvd_distance_flags_red_green_pair():
    # Pure red vs pure green collapse under deuteranomaly; two okabe-ito hues stay apart.
    clashing = cvd_min_distance(["#FF0000", "#00FF00"])
    distinct = cvd_min_distance(["#0072B2", "#E69F00"])
    assert clashing < distinct
    assert distinct > 15


def test_palette_registry_stable_and_baseline_grey():
    reg = PaletteRegistry()
    control = reg.assign("control")
    assert control.color == BASELINE_GREY

    a1 = reg.assign("patients")
    a2 = reg.assign("patients")  # stable on re-assignment
    assert a1 == a2
    assert a1.color != BASELINE_GREY

    b = reg.assign("responders")
    assert b.color != a1.color  # distinct groups get distinct colours
    # control retains its colour after later groups are added
    assert reg.assign("control").color == BASELINE_GREY
