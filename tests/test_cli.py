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


def test_lint_pie_blocks(tmp_path):
    p = tmp_path / "pie.svg"
    p.write_text(_PIE)
    result = runner.invoke(app, ["lint", str(p)])
    assert result.exit_code == 1
    assert "no_pie" in result.stdout


def test_lint_pie_override_passes(tmp_path):
    p = tmp_path / "pie.svg"
    p.write_text(_PIE)
    result = runner.invoke(app, ["lint", str(p), "--allow-override", "no_pie"])
    assert result.exit_code == 0
    assert "compliant" in result.stdout


def test_prompt_decline_exits_with_redirect():
    result = runner.invoke(app, ["prompt", "render the lesion t-map on the cortical surface"])
    assert result.exit_code == 2
    assert "Surf Ice" in result.stdout
