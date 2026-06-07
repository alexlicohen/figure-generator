# scidraw-agent

Prompt-driven scientific **schematic** generator with a built-in **Design Standards Engine**.

Turn a text prompt — or an ingested paper Methods section / grant Specific Aims — into an
**editable vector (SVG)** scientific schematic. Claude (Anthropic API) extracts a structured
figure description; open CC-licensed repositories (SciDraw via Zenodo, with a bioicons
fallback) supply organic shapes; generators draw the scaffold; and every output passes
through a standards-enforcement layer that silently applies publication and
visual-perception gold standards.

> **This is a schematic generator, not a neuroimaging renderer.** For real voxel data,
> statistical maps on anatomy, surface t/z-maps, or tractography, use **nilearn**
> (`plot_stat_map` / `plot_glass_brain`), **FSLeyes**, **MRIcroGL**, or **Surf Ice**. The
> tool detects such requests and declines with a redirect rather than faking a data render.

## Install

```bash
# system dependency for the pipeline/study-design generator + raster export
sudo apt-get install -y graphviz        # provides `dot`; cairo ships with most distros

uv venv && uv pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...      # only the extraction call uses the network
```

`scripts/setup.sh` does both steps idempotently (Graphviz + Python deps). For ephemeral
environments (e.g. Claude Code on the web) wire it as a `SessionStart` hook so tests can run
on a fresh container — add this to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "bash scripts/setup.sh" } ] }
    ]
  }
}
```

## Use

```bash
# from a prompt
scidraw prompt "corticospinal projection from M1 to spinal cord, with local inhibition" \
  --out fig --journal nature

# from a paper / grant
scidraw ingest paper.pdf --section methods --out fig
scidraw ingest aims.txt  --section aims    --out fig

# lint any SVG against the Design Standards Engine
scidraw lint figure.svg
scidraw lint figure.svg --allow-override no_pie   # documented per-figure escape hatch
```

Each run writes `figure.svg` (editable, text-as-text), a raster (`figure.png`), and
`figure.manifest.json` recording **license provenance** (each asset's DOI + license) and
**standards provenance** (applied fixes, honoured overrides, warnings).

### MCP server (Claude Code and other MCP clients)

```bash
claude mcp add --transport stdio scidraw -- python -m scidraw_agent.mcp_server
```

Tools: `schema_from_text`, `find_asset`, `compose_figure`, `lint_figure`, `list_rules`.

## Design Standards Engine

Standards are enforced centrally so **no generator can bypass them** — `style_guard`
runs on the final SVG of every generator:

- **Silent defaults** — Okabe-Ito categorical colour, Crameri colormaps (`vik` signed,
  `batlow` magnitude, `vikO` cyclic), stripped shadows/3D, removed frames, demoted
  gridlines, ≥0.25 pt strokes, text kept as text, journal sizing (Nature/Cell/Science/eLife).
- **BLOCK rules (strict, with a logged escape hatch)** — pie→refuse, jet/rainbow→Crameri,
  raw RGB→Okabe-Ito, red/green→accessible pair, sub-5 pt font→abort, neuro decline-triggers.
  A documented `--allow-override <rule>` downgrades a BLOCK to a manifest-logged entry.

See `docs/standards.md` for the full rule catalog with sources.

## Coverage honesty

SciDraw skews toward rodent / systems neuroscience; human clinical neuroanatomy is thin.
When no compatible asset is found, the figure degrades gracefully to a **labelled
placeholder** plus a warning, and (for brain/anatomy) points you at the real-render tools
above. Imported assets that are not CC-BY-compatible (NC / ND / SA / unknown) are **flagged
and excluded** by the license ledger.

## Privacy / local-first

Only the Claude extraction call touches the network at run time. Assets are cached after
first download, so warm-cache runs work offline. No hosted image generation; no
Chinese-jurisdiction image vendors.

## Develop

```bash
pytest -q          # full suite (mocks HTTP + Claude; one live bioicons download smoke test)
ruff check . && ruff format .
```

## License

MIT (code). Imported assets retain their own licenses, tracked per figure in
`figure.manifest.json`.
