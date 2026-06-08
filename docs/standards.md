# Design Standards catalog (sources)

This document is the citable record behind the Design Standards Engine. Each rule the
engine enforces (`standards/linter.py`) is tagged **[BLOCK]** (refuse / auto-convert,
overridable only via logged escape hatch), **[WARN]** (advisory), or **[DEFAULT]**
(applied silently), with the hard-coded value and an authoritative source.

> Populated milestone by milestone alongside `standards/linter.py` (M1). The summary below
> is the spine; per-rule source URLs are filled in as each rule is implemented.

## Color
- **[DEFAULT] Categorical = Okabe-Ito 8-colour** — Wong 2011, *Points of View: Color
  blindness*, Nat Methods. https://www.nature.com/articles/nmeth.1618
- **[DEFAULT] Sequential/magnitude = Crameri `batlow`; signed/diverging = `vik` (zero-locked);
  cyclic = `vikO`** — Crameri, Shephard & Heron 2020, Nat Commun.
  https://www.nature.com/articles/s41467-020-19160-7
- **[BLOCK] No jet/rainbow/turbo/hsv** for data encoding — Borland & Taylor 2007.
  https://pubmed.ncbi.nlm.nih.gov/17388198/
- **[BLOCK] No raw primary RGB; [BLOCK] no red/green-only contrast** — Wong 2011.

## Data-ink (Tufte)
- **[DEFAULT]** Hide top+right spines; gridlines `#B0B0B0`, behind data.
- **[BLOCK] No 3D for 2D quantitative data** (3D axes / shear-faked perspective) — matched on a
  fixed 3D vocabulary, never an arbitrary `3d` substring. No drop-shadows/bevels/decorative
  gradients. Tufte, *The Visual Display of Quantitative Information*.
  https://www.data-to-viz.com/caveat/3d.html
- **[DEFAULT] No hatch/pattern fills** → replaced with the pattern's solid colour (hatching
  causes moiré and prints poorly). https://www.data-to-viz.com/caveat.html
- **[WARN] Tick density** — thin to ~5–7 labelled ticks per axis.

## Decoding hierarchy (Cleveland & McGill 1984)
- **[BLOCK] No pie/donut for quantitative data** → sorted horizontal bar (slice values
  recovered from arc geometry; refused only when unrecoverable).
- **[WARN] Bubble area** — size must encode by area (radius ∝ √value), not radius.
  https://www.data-to-viz.com/caveat/radius_or_area.html

## Distribution rigor (data_plot, M8)
- **[BLOCK] No bar+SEM "dynamite" plot for continuous data** → show the distribution.
  Weissgerber et al. 2015, PLoS Biol.
  https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.1002128
- **[DEFAULT]** Geometry by sample size: n≤10 jittered dots; 10<n≤50 box + points;
  n>50 violin + box.
- **[DEFAULT]** Overplotting: point opacity scaled to n.
- **[DEFAULT] SuperPlot** for nested replicates (≥3): colour points by replicate, overlay
  replicate means, stats on N replicates. Lord et al. 2020, J Cell Biol.
  https://rupress.org/jcb/article/219/6/e202001064/151717
- **[DEFAULT] Stat reporting** — significance is shown with the exact p-value, n, and an
  effect size (Cohen's d / Hedges' g / rank-biserial r), not asterisks alone. Scatter/
  correlation reports Pearson r, p, n with a 95% mean-response band. Group brackets carry
  stars on the plot; the exact stats travel in the manifest for the legend.
  https://www.nature.com/articles/nphys4031

## Schematic semantics (neuro)
- **[DEFAULT]** Excitatory = filled pointed arrowhead; inhibitory = flat T-bar; modulatory
  = dashed/open — PMC, *Architectures of Neuronal Circuits*.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8916593/
- **[BLOCK] No false anatomical precision**; stylized brain glyphs tagged "schematic, not to scale".

## Neuroimaging decline-triggers
- **[BLOCK]** Real voxel data / stat maps on anatomy / surface t-maps / tractography →
  refuse and redirect to nilearn / FSLeyes / MRIcroGL / Surf Ice. The decline returns a
  *standards-baked render snippet* (`render_handoff.py`): Crameri colormap by data_kind,
  sign-preserving colorbar, journal figure size at print DPI, explicit L/R orientation.
- **[BLOCK]** Brain panels must declare orientation; **[DEFAULT]** neurological + L/R markers
  — NiBabel conventions. https://nipy.org/nibabel/neuro_radio_conventions.html

## Typography / layout / export
- **[BLOCK]** Font 5–7 pt at final size (floor 5 pt); **[BLOCK]** min stroke 0.25 pt.
- **[DEFAULT]** Journal presets — Nature (89/183 mm), Cell (85/174 mm), Science (57/121 mm),
  eLife (300 dpi); default Nature double-column, RGB, vector, Arial 7 pt.
- **Export** (`export.py`) — SVG (primary, editable) + PNG/PDF/EPS/TIFF. `figure_width`
  (single/double) sizes to the journal column in mm so vector physical size and raster
  px = DPI×size are both correct. TIFF is CMYK for CMYK journals (naive, non-colour-managed
  conversion — flagged; true CMYK wants the journal ICC profile).

## Accessibility
- **[BLOCK] Group → shape** — overlapping groups carry a redundant marker shape, not colour
  alone (guaranteed in the scatter generator). **[WARN] Text contrast** below 4.5:1 vs white
  (WCAG AA). **[WARN] Abbreviation legend** — define abbreviations in the caption.
  https://www.w3.org/TR/WCAG21/
