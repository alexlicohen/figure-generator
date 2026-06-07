# scidraw-agent

Prompt-driven scientific **schematic** generator with a built-in **Design Standards Engine**.

Turn a text prompt — or an ingested paper Methods section / grant Specific Aims — into an
editable vector (SVG) scientific schematic. Claude (Anthropic API) generates the scaffold
(layout, arrows, labels, flow geometry); open CC-licensed repositories (SciDraw via Zenodo,
with fallbacks) supply organic shapes; `svgutils` composes; and every output passes through
a standards-enforcement layer that silently applies publication and visual-perception gold
standards (Okabe-Ito / Crameri colour, Tufte data-ink, journal sizing, accessibility).

> **This is a schematic generator, not a neuroimaging renderer.** For real voxel data,
> statistical maps on anatomy, surface t/z-maps, or tractography, use **nilearn**,
> **FSLeyes**, **MRIcroGL**, or **Surf Ice** — the tool will decline and redirect you.

## Status

Under active development, milestone by milestone (see `/root/.claude/plans/`). Implemented:

- **M0** — project scaffold, data contracts (`FigureSchema`, `Manifest`), Claude wrapper.

## Install

```bash
uv venv && uv pip install -e ".[dev]"
# system deps for later milestones: graphviz (`dot`) and cairo
export ANTHROPIC_API_KEY=sk-ant-...
```

## License

MIT (code). Imported assets retain their own licenses, tracked per figure in
`figure.manifest.json`.
