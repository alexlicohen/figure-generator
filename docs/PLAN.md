<!-- Historical build plan (approved) for scidraw-agent. Preserved from the planning
     session; the implementation in this repo realises M0–M8 of this plan. -->

# scidraw-agent — Prompt-driven scientific schematic generator + Design Standards Engine

## Context

A pediatric neurology / neuroimaging researcher needs a local, scriptable tool that turns a **text prompt** — or an ingested **paper Methods section / grant Specific Aims** — into an **editable vector (SVG) scientific schematic**. Claude (Anthropic API) orchestrates and generates the non-organic scaffold; open CC-licensed repositories (SciDraw via Zenodo + fallbacks) supply organic shapes.

Beyond generation, the engine must **silently and strictly enforce the gold standards of scientific publication and human visual perception** — Tufte data-ink, Cleveland & McGill decoding hierarchy, Okabe-Ito / Crameri colour, Weissgerber/SuperPlots distribution rigor, journal figure specs, neuroimaging conventions, and accessibility. This is implemented as a cross-cutting **Design Standards Engine** that no generator can bypass.

The repo (`alexlicohen/figure-generator`) is **greenfield**. Output must be journal-grade, editable in Inkscape/Illustrator, and license-traceable (per-figure manifest with each asset's DOI + license).

**Locked decisions (from user):**
- Distribution = open-source/internal → **PyMuPDF (AGPL-3.0)** for PDF ingestion.
- Backends = **Lean**: Graphviz + svgutils/drawsvg + templated SVG + cairosvg export. Mermaid/TikZ/GROBID deferred behind interfaces.
- MCP = **FastMCP 3.x over stdio**.
- Standards scope = **Schematic-first**: Design Standards Engine enforces all *applicable* rules in v1; `data_plot` and `microscopy` generator modules are scaffolded behind the same engine as later milestones (no rework to add).
- BLOCK-tier rules = **strict with escape hatch**: enforced/auto-converted by default; a documented per-figure override (`StyleSpec.allow_overrides=[...]`) is honored and **recorded in the manifest** for provenance.

---

## Section 5 — Tooling research (ranked, weighted) — unchanged verdicts

- **Axis A (assets):** PRIMARY **SciDraw/Zenodo** (810; best organic neuro + queryable API + CC-BY); fallbacks **NIH BIOART** (human/clinical anatomy), **bioicons + Health Icons + PhyloPic**. Multi-backend `fetch.py` behind one `AssetBackend` protocol. ⚠️ Zenodo needs a real `User-Agent`; live `links.self` download is the M1 smoke-test gate. Reject Mind the Graph / BioRender / CC-NC / CC-SA.
- **Axis B (scaffold):** **Graphviz (8.35)** → `analysis_pipeline` + `study_design`; **templated raw SVG** → `mechanistic_circuit`; **svgutils compose** → `anatomical`. Correction: CONSORT → Graphviz, not Mermaid.
- **Axis C (compose):** **svgutils** primary (pin 0.3.4) + **drawsvg** (primitives) + **cairosvg** (export) + **svgpathtools** (anchor geometry) + **lxml** (surgical XML).
- **Axis D (ingest):** **PyMuPDF** + regex headings + **Claude fallback** (mandatory for grants). GROBID deferred opt-in.
- **Axis E (build vs adopt):** BUILD the text→schema→vector core (own the JSON IR); WRAP only OSS renderers + open icon sets. sci-draw.com/FigureLabs = closed SaaS, no API → competitors not deps. Watch SciFig.
- **Axis F (MCP):** **FastMCP 3.x over stdio.**

(Full weighted tables retained in git history of this plan; verdicts above are final.)

---

## Section 5b — Design Standards research (the new requirement)

~50 rules distilled into a machine-enforceable catalog. Each rule is tagged **[BLOCK]** (refuse / auto-convert; overridable only via logged escape hatch), **[WARN]** (advisory diagnostic), or **[DEFAULT]** (applied silently). Full per-rule sources captured in `docs/standards.md` at build time. Highest-leverage rules and the hard-coded values to ship:

### Color (silent, CVD-safe by construction)
- **[DEFAULT] Categorical = Okabe-Ito 8-color** (Wong 2011, Nat Methods): `#000000 #E69F00 #56B4E9 #009E73 #F0E442 #0072B2 #D55E00 #CC79A7`.
- **[DEFAULT] Sequential/magnitude = Crameri `batlow`** (or viridis/cividis fallback); **diverging/signed (t-/z-maps, %change) = Crameri `vik`** with midpoint locked to 0 (`TwoSlopeNorm(vcenter=0)`, symmetric `vmin=-vmax`); cyclic = `vikO`. Lib: `cmcrameri`.
- **[BLOCK] No jet/rainbow/hsv/turbo/nipy_spectral** for data encoding (Crameri 2020; Borland & Taylor 2007) → auto-replace with the rule-appropriate Crameri map.
- **[BLOCK] No raw primary RGB** (`#FF0000/#00FF00/#0000FF`, pure r/g/b/lime) → snap to nearest Okabe-Ito.
- **[BLOCK] No red/green as sole 2-class contrast** (overlays, edges, series) → remap to blue/orange or magenta/green.
- **[DEFAULT] Muted/gray baselines, saturated reserved for emphasis**: control/first group → `#999999`.

### Data-ink & decluttering (Tufte)
- **[DEFAULT]** Hide top+right spines; **[DEFAULT]** gridlines `#B0B0B0`, lw ≤ 0.5–0.8, `axisbelow=True` (behind data); major-only.
- **[BLOCK]** No 3D projection for 2D quantitative data; **[BLOCK]** no drop-shadows/bevels/gradient-fill on marks (strip `filter`, decorative gradients, `path_effects`); **[DEFAULT]** no hatch patterns, no redundant full frame.
- **[WARN]** ≤ 5–7 major ticks/axis; don't draw ticks + gridlines redundantly.

### Visual decoding hierarchy (Cleveland & McGill)
- **[BLOCK] No pie/donut for quantitative data** → auto-convert to sorted horizontal bar.
- **[DEFAULT]** Prefer position-on-common-scale > length > angle/area > color; **[WARN]** don't map the primary response to bubble area.

### Distribution rigor (Weissgerber; Lord SuperPlots) — *enforced when `data_plot` module lands*
- **[BLOCK] No bar/line "dynamite plot" for continuous data** → show points.
- **[DEFAULT]** Sample-size geom selection: n≤10 jittered dots; 10<n≲50 box + jittered points; n≳50 violin/box + points or 2D density.
- **[DEFAULT] SuperPlot** when nested replicates ≥3: color points by replicate, plot replicate means, stats on N replicates not n cells.

### Overplotting — *enforced when `data_plot` module lands*
- **[DEFAULT]** n≤1k opaque; 1k–10k alpha=clip(1000/n,0.05,0.3); 10k–1M hexbin/2D-hist; >1M datashader.

### Multi-panel consistency
- **[BLOCK] Stable group→color and group→shape mapping across all panels** (built once at figure scope; per-panel reassignment rejected) — persisted in the manifest.
- **[DEFAULT]** Shared axis ranges for like variables; panel letters **A,B,C** bold top-left; one shared legend.

### Schematic / diagram semantics (neuro)
- **[DEFAULT]** Gestalt grouping (proximity / similarity / subtle common-region tint) instead of bounding boxes.
- **[DEFAULT] Excitatory/projection = solid line + filled pointed arrowhead; inhibitory = flat T-bar head; modulatory = dashed/open** (consistent figure-wide). **[WARN]** never distinguish edge type by color alone.
- **[BLOCK] No false anatomical precision**: refuse stereotaxic coordinates on schematic glyphs; **[DEFAULT]** stylized brain glyphs auto-tagged "schematic, not to scale". **[WARN]** no decorative clipart; abbreviations must resolve to a legend.

### Neuroimaging decline-triggers (hard refusals → redirect)
- **[BLOCK]** Real voxel data (NIfTI/DICOM), stat maps overlaid on anatomy, surface t/z-maps, tractography/connectome in anatomical space → refuse and redirect: **nilearn `plot_stat_map`/`plot_glass_brain`, FSLeyes, MRIcroGL, Surf Ice**.
- **[BLOCK]** Any brain-like axial/coronal panel must declare orientation; **[DEFAULT]** neurological (mirror nilearn), burn-in L/R markers; **[WARN]** don't mix conventions in one figure.

### Microscopy/image — *enforced when `microscopy` module lands*
- **[BLOCK]** Mandatory burned-in scale bar (auto-sized ~1/5 width, high contrast); **[BLOCK]** preserve aspect ratio (no non-uniform scaling); **[DEFAULT]** 2-channel overlay = **magenta `#FF00FF` + green `#00FF00`**, never red/green; **[DEFAULT]** emit grayscale single channels alongside; **[WARN]** flag >0.1% clipped pixels.

### Typography, layout, export (journal presets)
- **[DEFAULT]** Sans-serif Arial/Helvetica; **[BLOCK]** font 5–7 pt at final size (floor 5 pt, default 7 pt); **[BLOCK]** min stroke 0.25 pt; constrained/tight layout (no cropped labels).
- **[DEFAULT] Export presets by journal:** Nature (single 89 mm / double 183 mm), Cell (85/174 mm, ≥7 pt), Science (57/121 mm, CMYK at revision), eLife (300 dpi). **Default = Nature double-column, RGB, vector PDF/SVG, Arial 7 pt, 0.25 pt min stroke.**
- **[DEFAULT/BLOCK]** Vector (SVG/PDF) preferred; raster floors line-art 1200 / combination 600 / halftone 300 dpi; **[DEFAULT]** keep SVG text as text (`svg.fonttype='none'`), embed PDF fonts (`pdf.fonttype=42`).
- **[WARN]** Text contrast ≥4.5:1 (normal) / 3:1 (large/graphical, WCAG 1.4.11).

---

## Design Standards Engine — architecture (the centerpiece)

The engine is **generator-agnostic and centralized** so enforcement is uniform and "often silent." Three cooperating components, all downstream of every generator:

1. **`StyleSpec` (Pydantic, `theme.py`)** — the single source of truth for every default above: palettes (Okabe-Ito, Crameri map names by data-kind), stroke weights, font/size, spine & gridline policy, journal preset (widths/dpi/colorspace), arrowhead semantics map, `allow_overrides: list[RuleId]`. Generators *consume* StyleSpec; they never hard-code style. Shipped also as a matplotlib `.mplstyle`/rcParams bundle for the future data_plot module so the same values drive both vector and plot output.

2. **`PaletteRegistry` (`palette.py`)** — builds the group→(color, shape, linestyle) mapping **once at figure scope** and hands the same mapping to every panel/generator; serialized into the manifest. Provides `snap_to_palette()` (raw-RGB → nearest Okabe-Ito), `colormap_for(data_kind)` (signed→vik / magnitude→batlow / categorical→Okabe-Ito / cyclic→vikO), and a CVD-distance check (`colorspacious` CAM02-UCS ΔE) run only when the user overrides colors.

3. **`style_guard.py` — post-render SVG enforcement pass (the silent layer).** Runs via `lxml` on the *output of every generator* (Graphviz, templated SVG, svgutils compose) before manifest emission:
   - **DEFAULT fixes (silent):** strip `<filter>` (drop shadows), decorative gradients, `style` shadows; remove Graphviz background rect + top/right frame; recolor strays to palette; demote gridlines (`#B0B0B0`, behind data); clamp strokes to ≥0.25 pt; keep `<text>` as text; inject stable group `id`s; add panel letters.
   - **BLOCK checks (abort/auto-convert unless rule ∈ `allow_overrides`):** pie/donut detected → convert to bar; jet/rainbow → replace; raw-RGB / red-green-only → remap; sub-5 pt text → abort with remediation; neuro decline-trigger → refuse + redirect message. Every applied conversion or honored override is logged to the manifest's `standards` block.
   - **WARN checks:** emit structured diagnostics (tick density, undefined abbreviations, contrast, mixed orientation) into `figure.manifest.json → standards.warnings`.

   `style_guard` is the architectural guarantee: because it operates on final SVG, **a non-compliant figure cannot be produced regardless of which generator (or future module) created it.**

4. **`linter.py`** — a thin façade exposing the BLOCK/WARN catalog as a reusable rule table (`RuleId → check + fix + source_url`), used by `style_guard`, by `extract.py` (to steer Claude's schema, e.g. tag edges excitatory/inhibitory), and as a standalone `scidraw lint figure.svg` command and MCP tool.

**Escape hatch:** `StyleSpec.allow_overrides=[RuleId,...]` (CLI `--allow-override no_pie`, MCP arg). A honored override downgrades that BLOCK to a logged WARN and is stamped into `manifest.standards.overrides` with the rule id + justification — provenance the user explicitly wanted.

---

## Where the original plan would have VIOLATED the constraints (and the fix)

| Risk in the v1-only plan | Fix in this revision |
|---|---|
| Graphviz default output has a white/background frame, system colors, `foreignObject`-free but un-themed nodes, drop-shadow-capable styles | `style_guard` strips frame/shadows, applies Okabe-Ito + Gestalt fills, post-processes every `dot -Tsvg` |
| Claude-emitted templated SVG could use raw RGB, red/green, pie-like glyphs, decorative shadows | `style_guard` BLOCK pass + `snap_to_palette`; circuit template pre-wired with excitatory/inhibitory arrowhead markers |
| svgutils compose could place panels with inconsistent per-asset colors / no panel letters / cropped labels | `PaletteRegistry` enforces one mapping; constrained layout + panel-letter injection; bbox check |
| No journal sizing / font-floor / stroke-floor | `StyleSpec` journal presets + `style_guard` clamps |
| Anatomical schematics could imply false precision; brain panels lacked L/R | decline-triggers + "schematic, not to scale" tag + mandatory orientation/L-R |
| Manifest tracked only license, not standards provenance | manifest gains a `standards` block (applied fixes, overrides, warnings) |

## Edge cases captured
- **Signed vs unsigned data colormap** auto-selection hinges on detecting a meaningful zero — default to magnitude/sequential unless schema/labels signal signed (t/z/Δ/correlation); WARN on ambiguous.
- **Override interaction:** an override for `no_red_green` must still pass CVD-distance or it re-warns.
- **Multi-panel with a new group in a later panel** — registry assigns next stable palette slot, never recolors existing groups.
- **Graphviz coordinate flip** can misplace injected panel letters — compute letter position in SVG user units after parsing, not in DOT.
- **Asset SVG carrying its own embedded styles/filters** — `style_guard` must scope-strip within the imported `<g>` without nuking legitimate organic shading (whitelist: keep fills that are the asset's data, strip only `filter`/shadow).
- **cairosvg raster export** must inherit the same stroke/font floors so PNG/PDF don't drop hairlines.

---

## Repo layout (updated)

```
scidraw-agent/
  pyproject.toml            # Python >=3.11, pinned deps
  CLAUDE.md                 # Section 2 constraints + "standards are non-negotiable defaults"
  docs/standards.md         # full rule catalog with per-rule source URLs (the citable record)
  src/scidraw_agent/
    config.py  models.py    # + StandardsReport, Manifest.standards block
    theme.py                # StyleSpec + journal presets + .mplstyle bundle      [NEW]
    palette.py              # PaletteRegistry, snap_to_palette, colormap_for, CVD [NEW]
    standards/                                                                    [NEW]
      linter.py             # RuleId catalog: check + fix + source_url
      style_guard.py        # post-render SVG enforcement (lxml) — the silent layer
    fetch.py  backends/{zenodo,bioicons,healthicons,phylopic}.py  registry.py
    ingest.py  extract.py   # extract.py emits standards-aware schema (edge polarity, data_kind)
    router.py
    generators/
      __init__.py           # Generator protocol (returns SVG -> always passes through style_guard)
      pipeline.py  circuit.py  anatomical.py
      # data_plot.py        # DEFERRED stub + interface (dynamite-block, SuperPlots, overplotting)
      # microscopy.py       # DEFERRED stub + interface (scale bar, aspect-lock, magenta/green)
    compose.py              # assembly + cairosvg export + manifest (license + standards)
    selfcheck.py  llm.py  cli.py  mcp_server.py
  tests/  fixtures/
```

### Dependencies (added vs base): `cmcrameri`, `colorspacious` (CVD ΔE). Base unchanged: `anthropic, pydantic>=2, requests, zenodo-get, svgutils==0.3.4, drawsvg>=2.4.1, svgpathtools>=1.7, lxml, cairosvg>=2.9, graphviz>=0.21 (+system dot, cairo), pymupdf>=1.24, fastmcp>=3.4, typer`. Dev: `pytest, pytest-mock, responses, ruff`. Deferred modules will add `matplotlib, seaborn, datashader` (data_plot) and `pillow, scikit-image` (microscopy).

---

## Milestone plan (build after approval; tests each gate)

**M0 — Scaffold.** Branch `claude/scidraw-agent-plan-Ef3oZ`; `pyproject.toml`, `CLAUDE.md`, package skeleton, `config.py`, `models.py` (FigureSchema + AssetRecord + Manifest **incl. `standards` block**), `llm.py`. Tests: model round-trips. *Gate: pytest green.*

**M1 — Design Standards Engine (foundational, built early on purpose).** `theme.py` (StyleSpec + Nature/Cell/Science/eLife presets), `palette.py` (Okabe-Ito cycle, `colormap_for` signed/magnitude/categorical/cyclic, `snap_to_palette`, CVD ΔE), `standards/linter.py` (RuleId catalog + source URLs → `docs/standards.md`), `standards/style_guard.py` (lxml DEFAULT strip/recolor/spine/stroke/text + BLOCK detect/convert + WARN diagnostics + escape-hatch logging). Tests: shadow/gradient stripped; jet→vik; raw-RGB→Okabe-Ito; pie→bar; sub-5pt aborts; red/green blocked; override honored + logged; CVD ΔE catches a clashing override. *Gate: a deliberately ugly input SVG comes out compliant; every BLOCK/WARN has a unit test.*

**M2 — Asset layer + license ledger (→ A6).** `fetch.py` + `AssetBackend`; `backends/zenodo.py` (real UA, live download smoke-test); `registry.py` cache + DOI/license ledger + CC-compat gate. Tests: mocked search/download; CC-BY-NC rejected; cache hit avoids refetch. *Gate: live Zenodo neuron SVG downloads; A6 enforced.*

**M3 — Generators + compose, all routed through style_guard (→ A1, A7).** `router.py`; `anatomical.py` (svgutils+drawsvg, Gestalt grouping, PaletteRegistry), `circuit.py` (templated SVG, excitatory/inhibitory arrowhead markers), `pipeline.py` (Graphviz→SVG); `compose.py` assembly + journal preset sizing + panel letters + cairosvg export + `figure.manifest.json` (license **+ standards** blocks). **Every generator output passes through `style_guard` before manifest.** Tests: each generator emits compliant SVG (no top/right spine, palette colors, ≥0.25pt strokes, text-as-text); manifest has both blocks; multi-panel keeps stable group mapping. *Gate: **A1** corticospinal figure opens in Inkscape, editable, compliant + manifest; **A7** standards block lists applied fixes.*

**M4 — Prompt→schema + self-check + neuro decline (→ A4, A8).** `extract.py` (prompt→FigureSchema, JSON-only, validate +1 repair, low temp; tags edge polarity + `data_kind`; emits neuro-decline when voxel/stat-map/tractography requested); `selfcheck.py` (omitted/invented entities; never invents anatomy); missing-asset → placeholder + warn + real-render suggestion. Tests: golden schema; placeholder path; invented-entity caught; **decline-trigger returns refusal + nilearn/Surf Ice redirect**; brain panel without orientation blocked. *Gate: **A4** placeholder; **A8** decline-trigger redirects correctly.*

**M5 — Methods/grant ingestion (→ A2, A3).** `ingest.py` (PyMuPDF blocks/fonts + regex headings + Claude fallback; `.pdf/.txt/.md/`paste). Wire ingest→extract→router→compose. Tests: lesion-network Methods → ordered `analysis_pipeline`, no invented steps; TSC Specific Aim → `study_design`/`mechanistic_circuit`, self-check zero invented. *Gate: **A2 + A3**.*

**M6 — MCP server + CLI (→ A5).** `mcp_server.py` FastMCP/stdio: `find_asset`, `schema_from_text`, `compose_figure`, **`lint_figure`**; `cli.py` (`prompt`, `ingest`, `lint`, `--journal`, `--allow-override`). Tests: in-process client per tool; `schema_from_text` valid; `compose_figure` returns SVG path; `lint_figure` returns standards report. *Gate: **A5**.*

**M7 — Hardening.** Network timeout+retry (exp backoff); offline-after-cache (only Claude extract hits network); README with SciDraw coverage-honesty note + "when to use a real render"; `docs/standards.md` finalized with sources. *Gate: full pytest green; offline warm-cache run.*

(Deferred behind the engine, post-v1: **M8 data_plot** — dynamite-block/box-violin-SuperPlots/overplotting via the shared `.mplstyle`; **M9 microscopy** — scale bar/aspect-lock/magenta-green/channel LUTs. Both consume StyleSpec + style_guard, so no engine rework.)

Commit per milestone; push to `claude/scidraw-agent-plan-Ef3oZ` with `-u origin` + exp-backoff retry. No PR unless requested.

---

## Acceptance criteria → milestone map
| ID | Criterion | Milestone |
|----|-----------|-----------|
| A1 | prompt → editable, **standards-compliant** figure.svg + manifest | M3 |
| A2 | lesion-network Methods → ordered analysis_pipeline, no invented steps | M5 |
| A3 | TSC Specific Aim → study_design/circuit, self-check zero invented | M5 |
| A4 | no-hit term → labeled placeholder + warning + real-render suggestion | M4 |
| A5 | MCP callable; schema_from_text valid; compose_figure → SVG; lint_figure → report | M6 |
| A6 | license ledger blocks/flags non-CC-BY-compatible assets | M2 |
| **A7** | **Standards enforced**: output has no top/right spine, no shadows/3D, palette-only colors, ≥0.25pt strokes, 5–7pt fonts, text-as-text; manifest `standards` block lists applied fixes; pie→bar & jet→vik auto-convert; raw-RGB & red/green blocked | M1 (engine) + M3 (integration) |
| **A8** | **Neuro integrity**: voxel/stat-map/tractography requests refuse + redirect (nilearn/Surf Ice); brain panels carry orientation + L/R; schematic glyphs tagged "not to scale"; escape-hatch override honored **and logged** in manifest | M1 + M4 |

## Verification (end-to-end)
1. `pytest -q` green per milestone (mocked HTTP/Claude; one live Zenodo smoke test in M2).
2. **A1/A7 manual:** `scidraw prompt "corticospinal projection M1 → spinal cord, labeled"`; open `figure.svg` in Inkscape — selectable groups, editable text, Okabe-Ito colors, no top/right spine, no shadows; inspect `figure.manifest.json` → `licenses` + `standards` (applied fixes, warnings, overrides).
3. **A7 adversarial:** feed a hand-made SVG containing a pie chart, jet colorbar, `#FF0000`/`#00FF00` pair, drop-shadow, 3pt font → confirm pie→bar, jet→vik, RGB snapped, shadow stripped, font-floor abort (or override logged).
4. **A8:** `scidraw prompt "render the patient's lesion t-map on the cortical surface"` → confirm refusal + Surf Ice/nilearn redirect; a coronal brain glyph prompt → confirm L/R + neurological tag + "not to scale".
5. **A2/A3:** `scidraw ingest fixtures/lesion_methods.txt` and the TSC aim → confirm type, ordered steps, zero invented (self-check report).
6. **A4:** no-SciDraw-hit term → placeholder + warning + real-render suggestion.
7. **A5:** `claude mcp add --transport stdio scidraw -- python -m scidraw_agent.mcp_server`; call each tool from Claude Code.
8. **A6:** register a CC-BY-NC asset → blocked/flagged.
9. **Offline:** warm cache, disable network, rerun a cached prompt — only Claude extract needs network.
