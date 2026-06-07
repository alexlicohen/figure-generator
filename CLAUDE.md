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

## Engineering conventions

- Python ≥3.11, `src/` layout, package `scidraw_agent`. Pin deps in `pyproject.toml`.
- All network calls wrapped with timeout + retry (exp backoff); cache downloaded SVGs.
- Zenodo requires a real `User-Agent` (default agents get HTTP 403) — see `config.USER_AGENT`.
- Tests with `pytest`; mock HTTP (`responses`) and the Claude call. One live Zenodo
  smoke test is allowed in the asset-layer tests.
- Lint/format with `ruff`.
