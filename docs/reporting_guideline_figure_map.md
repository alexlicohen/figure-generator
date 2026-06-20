# Reporting-guideline → mandated-figure map

Which reporting guideline mandates which figure, and how `scidraw-agent` supports it.
Use this when a manuscript targets a guideline and you need to know whether a flow
diagram is required and which template to build.

The four flow templates are built with `scidraw_agent.reporting.build_guideline_flow(name)`
(or the CLI `scidraw reporting <name>` / MCP `make_reporting_flow`). All four render through
the **one** flow engine — the Graphviz `PipelineGenerator` (`FigureType.REPORTING_FLOW`) — and
pass the same Design Standards Engine as every other figure. Counts in the boxes are *derived
and validated* from source data via `reporting.counts` (the cascade arithmetic), never invented.

> Attribution: the flow skeletons + count logic are reimplemented from the make-figures skill
> (Aperivue, MIT). See the repo-root `NOTICE`. This map is adapted from make-figures'
> `references/reporting_guideline_figure_map.md` (MIT).

## Mandatory-figure map

Legend — **Status**:
- shipped — `scidraw_agent.reporting` builds the flow skeleton (counts validated against source)
- generic — the flow generator covers the layout; no canonical-template fidelity check
- manual — no template; produce from the guideline document, then run the standards engine

| Guideline (year) | Study type | Mandatory figure(s) | Status |
|---|---|---|---|
| **PRISMA 2020** | Systematic review | 4-phase flow (identification → screening → eligibility → included) | shipped (`prisma`) |
| **PRISMA-DTA** | DTA systematic review | PRISMA flow + DTA-specific exclusion reasons | generic (build `prisma`, override exclusion-box labels) |
| **CONSORT 2025** | RCT | Participant-flow (enrollment → allocation → follow-up → analysis) | shipped (`consort`) |
| **CONSORT-AI 2020** | AI-intervention RCT | CONSORT flow + AI train/val/deploy dataset boxes | manual (extend `consort` with extra spine boxes) |
| **STARD 2015** | Diagnostic accuracy | Flow (eligible → index → reference standard → 2×2 TP/FP/FN/TN) + ROC | shipped (`stard`); ROC via `data_plot` |
| **STARD-AI 2025** | AI diagnostic accuracy | STARD flow + dataset-flow (train/tune/test) + subgroup ROC/PR | manual |
| **STROBE** | Observational cohort / case-control | Participant-flow (recommended, not strictly mandated) | shipped (`strobe`) |
| **TRIPOD 2015** | Prediction model | Calibration plot (mandatory) + discrimination (ROC, c-stat) | data plots (`data_plot` / `scatter`) |
| **TRIPOD+AI 2024** | AI prediction model | TRIPOD figures + fairness/subgroup panels + dataset-flow + decision-curve | manual (flow boxes + panels) |
| **CLAIM 2024** | Medical-imaging AI | Architecture diagram + dataset-flow + calibration + per-subgroup + saliency | manual (architecture via `analysis_pipeline`) |
| **SPIRIT 2025** | Trial protocol | Schedule-of-enrollment timeline | manual |
| **CARE 2013** | Case report | Timeline of patient course (recommended) | manual |

## Side-box exclusion cascade

The exclusion-reason boxes (CONSORT "Excluded", PRISMA "Records excluded", STROBE/STARD
"Excluded") are general schema features, not PRISMA-specific:

- `Entity.side_box = True` → drawn as a subordinate `note`-shaped annotation, not a spine node.
- `Entity.rank_with = "<spine_id>"` → placed on the same horizontal rank as the spine box it
  branches off (Graphviz `rank=same`).
- The connecting `Edge` carries `style="dashed", arrow=False, constraint=False` → a dashed,
  arrowless side branch that does not push the layout down a level.

## Count derivation (never invent counts)

Box counts come from the source data through `reporting.counts`:

- Build a `Cascade` of `FlowNode`s with the arithmetic relationships (`derive_from` + `excluded`
  for the screening waterfall; `split` for allocation / 2×2 branch points), then
  `derive_counts(cascade)` validates the arithmetic and returns the box counts. An invented or
  stale count (a box that does not follow from its inputs) raises `CountValidationError`.
- `extract_counts(text)` pulls the `n = N` / `TP = N` counts from a caption or label so a
  hand-written caption can be reconciled against the flow (the flow is the single source of truth).
- `selfcheck.flow_count_problems(schema)` checks conservation of inflow on the rendered schema
  (a box count may not exceed the sum of its solid-flow predecessors), wired into the existing
  `self_check` "don't invent entities" pass.
