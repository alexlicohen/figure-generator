# scidraw-agent

Prompt-driven scientific **schematic** generator with a built-in **Design Standards Engine**.

Turn a text prompt — or an ingested paper Methods section / grant Specific Aims — into an
**editable vector (SVG)** scientific schematic. Claude (Anthropic API) extracts a structured
figure description; open CC-licensed repositories supply organic shapes (SciDraw via Zenodo,
**NIH BIOART**, bioicons, **Wikimedia Commons** for human neuroanatomy, **Health Icons**, and
**PhyloPic** organism silhouettes — each asset's license is gated and recorded); generators
draw the scaffold; and every output passes
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

# distribution plot (no Claude call) — enforces no-dynamite / geom-by-n / SuperPlots
scidraw plot data.json --out fig            # data.json: {"groups": {"ctrl": [...], "tx": [...]}}

# multi-panel figure from a JSON list of schemas (shared palette, A/B/C letters)
scidraw panels schemas.json --out fig

# lint any SVG against the Design Standards Engine
scidraw lint figure.svg
scidraw lint figure.svg --allow-override no_pie   # documented per-figure escape hatch
```

Each run writes `figure.svg` (editable, text-as-text), a raster (`figure.png`),
`figure.manifest.json` recording **license provenance** (each asset's DOI + license) and
**standards provenance** (applied fixes, honoured overrides, warnings), and
`figure.credits.txt` — **paste-ready attribution** for your figure legend (a one-line credit
plus per-asset Title/Author/Source/License). Reused assets are credited in the **figure
legend**, not the bibliography; CC-BY assets must be credited, CC0/public-domain need not be.

### Editing the figure
Open `figure.svg` in **Inkscape** (free) or Illustrator/Affinity — groups are selectable and
text stays editable. Export to **PDF/EPS** (keep it vector) for submission; outline/embed
fonts only at the very end. Paste the credit line from `figure.credits.txt` into your legend.

### Use in a local Claude Code session (interactive)

The Claude extraction step can run two ways:

- **Subscription mode (no `ANTHROPIC_API_KEY`)** — Claude Code itself authors the
  `FigureSchema` (billed to your Claude subscription) and calls only the **local** tools to
  render. The package never calls the Anthropic API. This is the default when no key is set.
- **API mode (`ANTHROPIC_API_KEY` set)** — the package makes its own Claude call
  (`make_figure`, `scidraw prompt`). Pay-as-you-go API credits; best for scripts/automation.

Register the MCP server once (writes to your local Claude config — no repo changes):

```bash
claude mcp add scidraw -- uv run python -m scidraw_agent.mcp_server
```

In **subscription mode**, ask in natural language and Claude Code drives the *local* tools:
`check_decline` (refuse real-render requests) → author the schema → `self_check` (catch
invented entities / missing brain orientation) → `compose_figure` (render + enforce + manifest).
The `FigureSchema` authoring contract is in `CLAUDE.md`. CLI equivalent for a hand-written
or Claude-authored schema:

```bash
scidraw compose-schema schema.json --out fig      # no API call
```

Then, inside Claude Code in this repo, just ask in natural language — Claude calls the tools:

> "Make a figure of the corticospinal tract from M1 to spinal cord with local inhibition,
>  save it to ./fig."
> "Ingest methods.pdf and draw the analysis pipeline."
> "Find a CC-licensed thalamus asset."
> "Lint ./fig/figure.svg."

**Tools exposed:** `make_figure` (text → figure on disk, full pipeline), `make_figure_from_file`
(.pdf/.txt/.md → figure), `schema_from_text`, `find_asset`, `compose_figure`,
`make_data_plot` (distribution plot from a PlotRequest), `compose_panels_figure` (multi-panel
from several schemas), `lint_figure`, `list_rules`. `make_figure*`/`compose_*` fetch real
SciDraw/Zenodo + NIH BIOART assets by default (`use_assets`); `make_data_plot` and the local
tools never call the Anthropic API.

Requires `ANTHROPIC_API_KEY` in the environment Claude Code launches from.

To share the server with anyone who opens the repo, commit a project-scoped `.mcp.json`:

```json
{ "mcpServers": { "scidraw": { "command": "uv", "args": ["run", "--", "python", "-m", "scidraw_agent.mcp_server"] } } }
```

Plain CLI works too (Claude can run these in its terminal):

```bash
scidraw prompt "M1 projects to spinal cord" --out fig
scidraw ingest paper.pdf --section methods --out fig
scidraw lint fig/figure.svg
```

## Design Standards Engine

Standards are enforced centrally so **no generator can bypass them** — `style_guard`
runs on the final SVG of every generator:

- **Silent defaults** — Okabe-Ito categorical colour, Crameri colormaps (`vik` signed,
  `batlow` magnitude, `vikO` cyclic), stripped shadows/3D, removed frames, demoted
  gridlines, ≥0.25 pt strokes, text kept as text, journal sizing (Nature/Cell/Science/eLife).
- **BLOCK rules (strict, with a logged escape hatch)** — pie→**sorted bar** (auto-converted),
  jet/rainbow→Crameri, raw RGB→Okabe-Ito, red/green→accessible pair, sub-5 pt font→abort,
  neuro decline-triggers. A documented `--allow-override <rule>` downgrades a BLOCK to a
  manifest-logged entry.

See `docs/standards.md` for the full rule catalog with sources.

## Coverage honesty

SciDraw skews toward rodent / systems neuroscience. The asset chain backfills the rest:
**NIH BIOART** (public-domain human anatomy + MRI/PET/CT hardware), **Wikimedia Commons**
(human neuroanatomy SciDraw lacks — subcortical structures, slices, white-matter tracts; the
Servier SMART + DBCLS donations), **Health Icons** (CC0 medical line icons), and **PhyloPic**
(organism silhouettes for cohort panels). Coverage is still partial — when no compatible
asset is found, the figure degrades gracefully to a **labelled placeholder** plus a warning,
and (for brain/anatomy) points you at the real-render tools above. Imported assets that are
not CC-BY-compatible (NC / ND / SA /
unknown) are **flagged and excluded** by the license ledger; NIH BIOART is public domain.

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
