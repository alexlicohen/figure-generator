"""Paste-ready asset credit lines for the figure legend."""

from __future__ import annotations

from scidraw_agent.attribution import (
    asset_credit,
    build_credits,
    credits_text,
    figure_credit_line,
    license_label,
)
from scidraw_agent.models import AssetRecord


def _zenodo():
    return AssetRecord(
        query="pyramidal neuron",
        title="Pyramidal Neuron",
        backend="zenodo",
        doi="10.5281/zenodo.222",
        license="cc-by-4.0",
        creators=["Roe, R."],
    )


def _bioart():
    return AssetRecord(
        query="brain", title="Brain Lateral", backend="bioart", license="public-domain"
    )


def _placeholder():
    return AssetRecord(query="putamen", title="Putamen", backend="none", is_placeholder=True)


def test_license_label_handles_cc_variants_and_cc0():
    assert license_label("cc-by-4.0")[0] == "CC BY 4.0"
    assert license_label("cc-by-2.5")[0] == "CC BY 2.5"
    assert license_label("cc0-1.0")[0] == "CC0 1.0"
    assert license_label("public-domain")[0] == "public domain"
    assert license_label("cc-by-4.0")[1].startswith("https://creativecommons.org/licenses/by/")


def test_asset_credit_includes_title_author_source_license():
    c = asset_credit(_zenodo())
    assert '"Pyramidal Neuron"' in c
    assert "Roe, R." in c
    assert "SciDraw (via Zenodo)" in c
    assert "doi:10.5281/zenodo.222" in c
    assert "CC BY 4.0" in c


def test_asset_credit_placeholder_is_none():
    assert asset_credit(_placeholder()) is None


def test_figure_credit_line_combines_and_dedups():
    line = figure_credit_line([_zenodo(), _zenodo(), _bioart(), _placeholder()])
    assert line.startswith("Illustrative assets adapted from open repositories:")
    assert line.count('"Pyramidal Neuron"') == 1  # deduplicated
    assert '"Brain Lateral"' in line
    assert "Putamen" not in line  # placeholder excluded


def test_build_credits_flags_cc_by_attribution_required():
    assert build_credits([_zenodo(), _bioart()]).attribution_required is True
    assert build_credits([_bioart()]).attribution_required is False  # CC0/PD only
    assert build_credits([_placeholder()]).per_asset == []


def test_credits_text_states_requirement_and_distinguishes_references():
    txt = credits_text(build_credits([_zenodo()]))
    assert "MUST be credited" in txt
    assert "not bibliography references" in txt
    assert "── Legend credit line ──" in txt

    txt_cc0 = credits_text(build_credits([_bioart()]))
    assert "credit not required" in txt_cc0
