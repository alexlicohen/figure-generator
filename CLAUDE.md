# scidraw-agent — conventions & constraints

Prompt-driven scientific schematic generator for a pediatric neurology / neuroimaging
researcher. Claude (Anthropic API) generates the non-organic scaffold; open CC-licensed
repositories supply organic shapes; a **Design Standards Engine** silently enforces
publication and visual-perception gold standards on every output.

## Hard constraints (Section 2 of the brief — bake these in)

- **Vector-native, editable.** SVG first; PNG/PDF export secondary. Output must open
  cleanly in Inkscape/Illustrator with selectable groups and **text kept as text**.
  Never rasterize anatomy into the final figure.
- **Licensing discipline.** Every imported asset carries its DOI + license into
  `figure.manifest.json`. The ledger BLOCKS/flags anything not CC-BY-compatible
  (reject CC-BY-NC, CC-BY-SA unless the user explicitly opts in).
- **Privacy / local-first.** Only the Claude extraction call hits the network at run
  time; everything else works offline once assets are cached. No hosted image-gen, and
  **no Chinese-jurisdiction vendors** (SeeDream/ByteDance, Kling).
- **Honesty about coverage.** SciDraw skews rodent/systems-neuro; human clinical
  neuroanatomy is thin. Degrade gracefully (scaffold + labelled placeholder) and tell
  the user when a real data render (nilearn / Surf Ice / MRIcroGL / FSLeyes) is correct.

## Design Standards Engine (non-negotiable defaults)

Standards are enforced centrally so no generator can bypass them:

- `theme.py` — `StyleSpec`: palettes, stroke/font floors, spine/grid policy, journal presets.
- `palette.py` — stable group→(colour, shape) mapping across panels; Okabe-Ito categorical;
  Crameri colormaps (`vik` signed, `batlow` magnitude, `vikO` cyclic).
- `standards/style_guard.py` — post-render lxml pass on **every** generator's SVG:
  strips shadows/3D/decorative gradients, removes top/right spines, demotes gridlines,
  clamps strokes ≥0.25pt, keeps text as text; BLOCK checks (pie→bar, jet→vik, raw-RGB &
  red/green remap, sub-5pt abort, neuro decline-triggers); WARN diagnostics.
- `standards/linter.py` — the `RuleId → (check, fix, source_url)` catalog.

BLOCK rules are **strict with an escape hatch**: enforced/auto-converted by default; a
documented per-figure override (`StyleSpec.allow_overrides`) is honoured and **logged in
the manifest's `standards` block**.

## LLM usage (Anthropic API)

- Default model `claude-opus-4-8` (see `config.py`). Opus 4.8 has **no**
  `temperature`/`top_p`/`top_k` and **no** `budget_tokens` — do not add them (they 400).
  Determinism for extraction comes from **structured outputs** (`messages.parse` with a
  Pydantic schema) + low `effort`, not sampling params.
- API key from `ANTHROPIC_API_KEY` env only — never hardcode.

## Two run modes (subscription vs API)

The Claude **extraction** call is the only LLM step. It can run two ways:

- **Subscription mode (no `ANTHROPIC_API_KEY`).** *You, Claude Code,* author the
  `FigureSchema` from the user's text — billed to the user's Claude subscription — then call
  only the **local** MCP tools / CLI to render. Workflow:
  1. `check_decline(text)` — if `declined`, STOP and give the user the listed real-render
     tools (nilearn/FSLeyes/MRIcroGL/Surf Ice); do **not** draw a schematic.
  2. Author a `FigureSchema` (contract below). Do **not** invent entities/steps/anatomy not
     supported by the text.
  3. `self_check(schema, source_text=...)` — surface invented-entity / brain-orientation /
     dangling-edge warnings; fix and re-author if needed.
  4. `compose_figure(schema, out_dir, use_assets=true)` (MCP) or
     `scidraw compose-schema schema.json --out DIR` (CLI). Renders + enforces standards +
     writes the manifest. No API key needed.
- **API mode (`ANTHROPIC_API_KEY` set).** `make_figure` / `schema_from_text` /
  `scidraw prompt|ingest` make their own Claude call. For non-interactive / scripted use.

### FigureSchema authoring contract (subscription mode)
- `figure_type`: `mechanistic_circuit` (neural/molecular wiring) · `analysis_pipeline`
  (ordered steps) · `study_design` (cohorts/arms) · `anatomical` (labelled structures) ·
  `data_plot` (distributions — use `compose_data_plot`/`PlotRequest`, not this schema).
- `entities[]`: `id` (short, edge-referenced), `label`, `kind`
  (`region|celltype|modality|cohort|step|other`), optional `suggested_asset_query` (for
  organic structures, e.g. "pyramidal neuron"), optional `group` (stable colour per group).
- `edges[]`: `source`, `target` (entity ids), `relation` — polarity matters:
  `excites|projects_to|flows_to` (excitatory/forward), `inhibits` (inhibitory),
  `modulates` (neuromodulatory), `predicts`, `other`.
- `data_kind`: `none` unless colour encodes a quantity (`signed` t/z/%-change, `magnitude`
  one-sided, `categorical`, `cyclic`).
- Brain slices (axial/coronal/sagittal): state orientation (neurological/radiological) and
  L/R in the label, or `self_check` flags it.
- `caption_seed`: one sentence grounded strictly in the input.

## Engineering conventions

- Python ≥3.11, `src/` layout, package `scidraw_agent`. Pin deps in `pyproject.toml`.
- All network calls wrapped with timeout + retry (exp backoff); cache downloaded SVGs.
- Zenodo requires a real `User-Agent` (default agents get HTTP 403) — see `config.USER_AGENT`.
- Tests with `pytest`; mock HTTP (`responses`) and the Claude call. One live Zenodo
  smoke test is allowed in the asset-layer tests.
- Lint/format with `ruff`.

## Project status (handoff memory — updated 2026-06-07)

**Done & merged (PR #1 → `main`).** Milestones M0–M8 complete; 73 tests green; ruff clean.
- M0 scaffold (`models` IR, `config`, `llm`) · M1 Design Standards Engine (`theme`,
  `palette`, `standards/{linter,style_guard}`) · M2 asset layer + license ledger
  (`fetch`, `registry`, `backends/{zenodo,bioart,bioicons,wikimedia,healthicons,phylopic}`) · M3 generators + compose
  (`generators/{circuit,pipeline,anatomical,data_plot}`, `router`, `compose`) ·
  M4 `extract` (neuro-decline gate) + `selfcheck` · M5 `ingest` + `run` · M6
  `mcp_server` + `cli` · M7 README/`scripts/setup.sh` · M8 `data_plot`.
- **M9 microscopy: SKIPPED permanently** — user does MRI/neuroimaging only. Do not build it.

**Architecture invariant:** every generator returns SVG that `compose` runs through
`standards.enforce` before writing; raster (cairosvg) inherits the guarded SVG. Add new
generators behind the `Generator` protocol + `router`; never bypass the guard.

**Pipeline:** `run.figure_from_text/file` → `ingest` (section) → `extract` (Claude
structured outputs, neuro-decline gate first) → `selfcheck` → `route` → generator →
`style_guard.enforce` → `compose` writes `figure.svg` + `figure.png` + `figure.manifest.json`
(license + standards blocks).

**Environment facts:**
- System dep: Graphviz `dot` (pipeline/study-design). `scripts/setup.sh` installs it +
  deps; verified working. SessionStart hook NOT committed (permission guard blocked it;
  user to add `.claude/settings.json` manually if wanted).
- Network: only the Claude `extract` call hits the net at runtime; assets cached after
  first fetch. The original build sandbox blocked `zenodo.org` (host allowlist) so SciDraw
  fell back to placeholders + the bioicons fallback. **Local dev now has Zenodo access** —
  expect real SciDraw assets for `anatomical` figures.
- LLM: `claude-opus-4-8`; structured outputs + low `effort` (no temperature/budget_tokens).
  `ANTHROPIC_API_KEY` from env only.

**Done since the M0–M8 handoff (PR: plan-gaps-and-assets, 92 tests):**
- **pie→bar auto-converts** in `style_guard` (recovers slice fractions from arc geometry,
  clustering wedges by shared centre → sorted horizontal bar; refuses only when slice values
  are unrecoverable). Closes the A7 gap.
- **NIH BIOART backend** (`backends/bioart.py`) — public-domain human/clinical-anatomy vector
  SVGs, the SciDraw coverage gap. BIOART has no stable API (search + downloads run through
  per-deploy Next.js server actions), so it uses a curated package-shipped index
  (`bioart_index.json`: id, resolved SVG file_id, title, keywords) + the one stable endpoint
  `/api/bioarts/{id}/files/{file_id}`. Priority: Zenodo → BIOART → bioicons.
- **`data_plot` + `compose_panels` now have CLI + MCP surfaces:** `scidraw plot data.json`,
  `scidraw panels schemas.json`; MCP `make_data_plot`, `compose_panels_figure` (both local /
  no-API).
- **Raster is best-effort/lazy** (`compose._export_raster` no longer hard-imports cairosvg —
  SVG always ships; PNG/PDF skipped-with-warning if libcairo is absent — matches the
  SVG-first brief).
- **macOS dev env:** `scripts/setup.sh` installs graphviz+cairo via brew; `compose._ensure_
  cairo_discoverable()` points cffi at Homebrew's libcairo before the lazy cairosvg import,
  so both the test suite and the real CLI/MCP emit PNG with no manual env (darwin-only no-op).
- **Live asset access verified locally:** Zenodo (the cloud sandbox's blind spot), bioicons,
  and BIOART all download real assets; `test_fetch_live.py` covers all three (auto-skip when
  a host is unreachable).
- **Zenodo relevance fixed:** `sort=bestmatch` (not `mostviewed`) + a title-relevance gate
  (`_title_relevant`) so a term SciDraw lacks (e.g. "thalamus") returns nothing → graceful
  fallback, instead of a popular off-topic deposit ("pyramidal neuron" → "mouse").
- **BIOART index expanded + corrected (14 → 23):** added neuroimaging hardware (MRI incl.
  Neonatal, PET, CT). The original blind-probe ids were partly wrong (the file proxy ignores
  the `{id}` path; ids interleave) — e.g. 688 pointed at item 689's MRI. All ids are now
  resolved authoritatively from each item page's RSC `filemapping` (`"SVG"` value).

- **Three asset backends added (now 6 total).** Priority: Zenodo → BIOART → bioicons →
  **Wikimedia** → **Health Icons** → **PhyloPic**.
  - `backends/wikimedia.py` — Commons MediaWiki API; fills human neuroanatomy (thalamus,
    hippocampus, slices, tracts; Servier SMART + DBCLS donations). Mixed-license, so per-file
    license read from `imageinfo extmetadata` and gated (CC-BY-SA/non-free rejected); SVG-only.
  - `backends/healthicons.py` — CC0 medical line icons via `meta-data.json` index; title
    matches ranked before tag-only (Brain, Nerve, Skull, Head Circumference).
  - `backends/phylopic.py` — organism silhouettes (build-versioned HATEOAS API);
    per-image CC license mapped + gated. `backends/_text.py` holds shared token/relevance helpers.
  - Live coverage in `test_fetch_live.py` for all three (auto-skip if a host is unreachable).

- **Circuit generator rebuilt on Graphviz** (`generators/circuit.py`). The old single-row
  drawsvg layout drew non-adjacent edges *through* intermediate nodes (e.g. M1→cord with an
  interneuron between them), misrepresenting the circuit. Now Graphviz lays it out (rankdir=LR);
  edge polarity via arrowhead shape (`normal` excitatory / `tee` inhibitory / `empty`+dashed
  modulatory); a compact legend is appended as SVG for the relation types present. `drawsvg`
  dependency dropped (was its only user).
- **Anatomical contrast fix** — `anatomical._boost_contrast` darkens pale *achromatic* asset
  fills/strokes (e.g. SciDraw's all-pale-grey pyramidal neuron that vanished on white) while
  sparing light *coloured* fills (a diagram's pale-teal regions). Light+low-channel-spread only.
- **Paste-ready credits** (`attribution.py`) — compose writes `figure.credits.txt` + a `credits`
  block in the manifest. Default `legend_line` is the **compact** convention (grouped by
  source+license, titles dropped, authors as initials — CC's "reasonable to the medium");
  `legend_line_full` keeps the full CC TASL (Title/Author/Source(+DOI)/License); plus per-asset
  lines. Reused assets are credited in the figure legend, NOT the bibliography; CC-BY ⇒
  attribution_required. Surfaced in the CLI `_emit` and MCP `_manifest_summary`.
- Output quality spot-checked by rendering anatomical/circuit/pipeline/data_plot with real
  assets and visually inspecting the PNGs (pipeline + data_plot were already publication-grade).

**Known follow-ups (not yet built):** BIOART neuro depth is shallow (no synapse / microglia /
spinal-cord / EEG); Wikimedia is broad but quality varies; PhyloPic matches taxonomic names
best (common names like "mouse" may miss). Sequential pipelines get one Okabe-Ito colour per
step (slightly rainbow) — could shade by a single hue. All handled by graceful degradation.
