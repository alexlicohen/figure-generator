"""M6: CLI commands (Typer CliRunner)."""

from __future__ import annotations

from typer.testing import CliRunner

from scidraw_agent.cli import app

runner = CliRunner()

_COMPLIANT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40" viewBox="0 0 60 40">'
    '<rect x="5" y="5" width="20" height="12" fill="#0072B2"/>'
    '<text x="8" y="14" font-size="12" font-family="Arial">M1</text></svg>'
)

_PIE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'
    + "".join(
        f'<path d="M50,50 L90,50 A40,40 0 0 1 {x},{y} Z" fill="#0072B2"/>'
        for x, y in [(70, 86), (20, 70), (40, 18)]
    )
    + "</svg>"
)


def test_lint_compliant(tmp_path):
    p = tmp_path / "ok.svg"
    p.write_text(_COMPLIANT)
    result = runner.invoke(app, ["lint", str(p)])
    assert result.exit_code == 0
    assert "compliant" in result.stdout


def test_lint_pie_auto_converts(tmp_path):
    # A7: pie auto-converts to a sorted bar — lint passes and reports the fix.
    p = tmp_path / "pie.svg"
    p.write_text(_PIE)
    result = runner.invoke(app, ["lint", str(p)])
    assert result.exit_code == 0
    assert "no_pie" in result.stdout
    assert "compliant" in result.stdout


def test_lint_pie_override_passes(tmp_path):
    p = tmp_path / "pie.svg"
    p.write_text(_PIE)
    result = runner.invoke(app, ["lint", str(p), "--allow-override", "no_pie"])
    assert result.exit_code == 0
    assert "compliant" in result.stdout


def test_compose_schema_renders_locally(tmp_path):
    schema = (
        '{"figure_type": "mechanistic_circuit", '
        '"entities": [{"id": "m1", "label": "M1"}, {"id": "sc", "label": "Spinal cord"}], '
        '"edges": [{"source": "m1", "target": "sc", "relation": "projects_to"}]}'
    )
    sp = tmp_path / "schema.json"
    sp.write_text(schema)
    result = runner.invoke(
        app, ["compose-schema", str(sp), "--out", str(tmp_path / "out"), "--no-assets"]
    )
    assert result.exit_code == 0, result.stdout
    assert "figure:" in result.stdout
    assert (tmp_path / "out" / "figure.svg").exists()


def test_prompt_decline_exits_with_redirect():
    result = runner.invoke(app, ["prompt", "render the lesion t-map on the cortical surface"])
    assert result.exit_code == 2
    assert "Surf Ice" in result.stdout


def test_plot_renders_distribution(tmp_path):
    data = tmp_path / "data.json"
    data.write_text(
        '{"groups": {"control": [1,2,3,2,1,2.5], "treated": [3,4,5,4,3,4.5]}, "ylabel": "signal"}'
    )
    result = runner.invoke(app, ["plot", str(data), "--out", str(tmp_path / "out")])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "out" / "figure.svg").exists()


def test_plot_dynamite_blocks(tmp_path):
    data = tmp_path / "data.json"
    data.write_text('{"groups": {"a": [1,2,3], "b": [4,5,6]}, "force_kind": "bar"}')
    result = runner.invoke(app, ["plot", str(data), "--out", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert "no_dynamite" in result.stdout


def test_plot_dynamite_override_renders(tmp_path):
    data = tmp_path / "data.json"
    data.write_text('{"groups": {"a": [1,2,3], "b": [4,5,6]}, "force_kind": "bar"}')
    result = runner.invoke(
        app, ["plot", str(data), "--out", str(tmp_path / "out"), "--allow-override", "no_dynamite"]
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "out" / "figure.svg").exists()


def test_panels_renders_multipanel(tmp_path):
    schemas = tmp_path / "panels.json"
    schemas.write_text(
        '[{"figure_type": "mechanistic_circuit", '
        '"entities": [{"id": "a", "label": "Patients", "group": "patients"}]}, '
        '{"figure_type": "mechanistic_circuit", '
        '"entities": [{"id": "b", "label": "Controls", "group": "control"}]}]'
    )
    result = runner.invoke(
        app, ["panels", str(schemas), "--out", str(tmp_path / "out"), "--no-assets"]
    )
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "out" / "figure.svg").exists()
