"""Prompt/text -> FigureSchema via Claude structured outputs, with a neuro-decline gate.

The decline gate runs *before* any model call: requests for real neuroimaging renders
(voxel data, statistical maps on anatomy, surface t/z-maps, tractography) are refused and
redirected to the correct tools, because a schematic must never stand in for a data render.
Extraction uses `messages.parse` (structured output) so the schema is valid by construction;
one repair retry covers transient model failures.
"""

from __future__ import annotations

import re

from .config import Config, load_config
from .llm import LLMClient
from .models import FigureSchema
from .standards.linter import RuleId, rule

# Tools the user should reach for instead of a schematic.
REAL_RENDER_TOOLS = [
    "nilearn (plot_stat_map / plot_glass_brain)",
    "FSLeyes",
    "MRIcroGL",
    "Surf Ice",
]

# Patterns that signal a real-data neuroimaging render (decline + redirect). Tuned to avoid
# firing on legitimate schematic/methods language (e.g. "lesion network mapping").
_DECLINE_PATTERNS = [
    r"\bvoxel(?:wise|-wise|s)?\b",
    r"\bnifti\b",
    r"\.nii(?:\.gz)?\b",
    r"\bdicom\b",
    r"\btractograph",
    r"\bstreamlines?\b",
    r"\bglass brain\b",
    r"\bplot_(?:stat_map|glass_brain)\b",
    r"\b[tz][-\s]?map\b",
    r"\bstat(?:istical)?[-\s]map\b",
    r"\bactivation map\b",
    r"\bconnectome\b.*\b(space|render|anatom)",
    r"render(?:ing)?\b.{0,40}\b(lesion|t-?map|z-?map|activation|overlay)\b.{0,40}"
    r"\b(surface|cortex|cortical|brain|anatomy|mni)\b",
    r"\boverlay\b.{0,40}\b(anatomy|brain|cortex|cortical|surface|mni)\b",
    r"\bfmri\b.{0,40}\bactivation\b",
]
_DECLINE_RE = [re.compile(p, re.IGNORECASE) for p in _DECLINE_PATTERNS]


class NeuroDeclineError(Exception):
    """Raised when a prompt asks for a real neuroimaging render rather than a schematic."""

    def __init__(self, matched: str) -> None:
        self.matched = matched
        self.tools = REAL_RENDER_TOOLS
        r = rule(RuleId.NEURO_DECLINE)
        super().__init__(
            f"This request ('{matched}') needs a real data render, not a schematic. "
            f"Use: {', '.join(REAL_RENDER_TOOLS)}. ({r.source_url})"
        )


def neuro_decline_trigger(text: str) -> str | None:
    """Return the matched phrase if the text requests a real neuroimaging render, else None."""
    for rx in _DECLINE_RE:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


SYSTEM_PROMPT = """\
You convert a researcher's description into a FigureSchema for a scientific SCHEMATIC.

Rules:
- Choose figure_type: mechanistic_circuit (neural/molecular wiring), analysis_pipeline
  (ordered processing steps), study_design (cohorts/arms/timeline), or anatomical
  (labelled structures).
- Create one entity per real thing named or clearly implied. Do NOT invent entities,
  steps, regions, or anatomy that the text does not support.
- Give each entity a short id, a human label, a kind, and (for organic structures) a
  suggested_asset_query. Use `group` to cluster related entities (stable colour per group).
- For edges, set relation to the correct polarity: excites/projects_to/flows_to for
  excitatory or forward flow, inhibits for inhibitory, modulates for neuromodulatory.
- Set data_kind only if the figure encodes a quantity by colour (signed for t/z/%-change,
  magnitude for one-sided, categorical, cyclic), else none.
- For any brain slice (axial/coronal/sagittal), state the orientation convention
  (neurological or radiological) and include L/R in the label.
- Write a one-sentence caption_seed grounded strictly in the input.
"""

_REPAIR_SUFFIX = "\nReturn ONLY a valid FigureSchema. Do not add entities absent from the input."


def extract(
    prompt: str,
    *,
    llm: LLMClient | None = None,
    config: Config | None = None,
) -> FigureSchema:
    """Extract a FigureSchema from free text. Raises NeuroDeclineError on decline triggers."""
    matched = neuro_decline_trigger(prompt)
    if matched:
        raise NeuroDeclineError(matched)

    config = config or load_config()
    llm = llm or LLMClient(config)
    try:
        return llm.parse(FigureSchema, system=SYSTEM_PROMPT, user=prompt)
    except Exception:
        # one repair retry — transient model/parse failure
        return llm.parse(FigureSchema, system=SYSTEM_PROMPT + _REPAIR_SUFFIX, user=prompt)
