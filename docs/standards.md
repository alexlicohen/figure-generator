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
- **[BLOCK]** No 3D for 2D quantitative data; no drop-shadows/bevels/decorative gradients.
  Tufte, *The Visual Display of Quantitative Information*.

## Decoding hierarchy (Cleveland & McGill 1984)
- **[BLOCK] No pie/donut for quantitative data** → sorted horizontal bar.

## Schematic semantics (neuro)
- **[DEFAULT]** Excitatory = filled pointed arrowhead; inhibitory = flat T-bar; modulatory
  = dashed/open — PMC, *Architectures of Neuronal Circuits*.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC8916593/
- **[BLOCK] No false anatomical precision**; stylized brain glyphs tagged "schematic, not to scale".

## Neuroimaging decline-triggers
- **[BLOCK]** Real voxel data / stat maps on anatomy / surface t-maps / tractography →
  refuse and redirect to nilearn / FSLeyes / MRIcroGL / Surf Ice.
- **[BLOCK]** Brain panels must declare orientation; **[DEFAULT]** neurological + L/R markers
  — NiBabel conventions. https://nipy.org/nibabel/neuro_radio_conventions.html

## Typography / layout / export
- **[BLOCK]** Font 5–7 pt at final size (floor 5 pt); **[BLOCK]** min stroke 0.25 pt.
- **[DEFAULT]** Journal presets — Nature (89/183 mm), Cell (85/174 mm), Science (57/121 mm),
  eLife (300 dpi); default Nature double-column, RGB, vector, Arial 7 pt.

## Accessibility
- **[DEFAULT]** Redundant encoding (colour + shape/linestyle). **[WARN]** WCAG contrast
  ≥4.5:1 text / 3:1 graphical. https://www.w3.org/TR/WCAG21/
