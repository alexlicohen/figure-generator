"""Turn a neuro-decline into a head start.

When a request needs a *real* data render (stat map on anatomy, glass brain, surface/
tractography overlay), the schematic generator must decline (``RuleId.NEURO_DECLINE``). But
declining is more useful when it hands back ready-to-run code than a bare tool list. This
module emits a standards-baked snippet for the right tool — perceptually-uniform Crameri
colormap, sign-preserving symmetric colorbar, journal figure size at the print DPI, and an
explicit L/R orientation convention — so the researcher pastes and runs instead of starting cold.

Pure string assembly; imports nothing heavy. The colormap choice follows the same DataKind
policy the style_guard uses for SVG gradients (signed→vik, magnitude→batlow, cyclic→vikO).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .models import DataKind
from .theme import StyleSpec


class RenderKind(StrEnum):
    GLASS_BRAIN = "glass_brain"
    STAT_MAP = "stat_map"
    SURFACE = "surface"
    CONNECTOME = "connectome"
    TRACTOGRAPHY = "tractography"


# Which real-render kind a decline phrase implies. First match wins; order = most specific first.
_KIND_PATTERNS: list[tuple[RenderKind, str]] = [
    (RenderKind.GLASS_BRAIN, r"glass[\s-]?brain|plot_glass_brain"),
    (RenderKind.TRACTOGRAPHY, r"tractograph|streamline|\bdti\b|\bdwi\b|fiber|fibre"),
    (RenderKind.CONNECTOME, r"connectom|\bedge bundl|node[\s-]?link.*brain"),
    (RenderKind.SURFACE, r"surface|\bpial\b|inflated|\bgifti\b|surf ice|freesurfer"),
    (
        RenderKind.STAT_MAP,
        r"stat(?:istical)?[\s-]?map|[tz][\s-]?map|activation|voxel|\.nii|nifti|overlay",
    ),
]
_KIND_RE = [(k, re.compile(p, re.IGNORECASE)) for k, p in _KIND_PATTERNS]

# DataKind -> (cmcrameri colormap, whether the colorbar should be symmetric about zero).
_CMAP = {
    DataKind.SIGNED: ("vik", True),
    DataKind.MAGNITUDE: ("batlow", False),
    DataKind.CYCLIC: ("vikO", False),
    DataKind.NONE: ("vik", True),
    DataKind.CATEGORICAL: ("batlowS", False),
}


@dataclass(frozen=True)
class RenderHandoff:
    """A paste-ready render recipe for a real-data neuroimaging figure."""

    kind: RenderKind
    tool: str  # "nilearn" | "Surf Ice"
    code: str
    notes: list[str]


def choose_render_kind(text: str) -> RenderKind:
    """Map a decline trigger / request text to the most appropriate render kind."""
    for kind, rx in _KIND_RE:
        if rx.search(text):
            return kind
    return RenderKind.STAT_MAP


def _figsize_in(style: StyleSpec) -> tuple[float, float]:
    """Journal double-column width in inches, with a 5:3-ish brain aspect."""
    w_in = style.preset.double_col_mm / 25.4
    return round(w_in, 2), round(w_in * 0.6, 2)


def _orientation_note(orientation: str) -> str:
    o = orientation.strip().lower()
    if o.startswith("rad"):
        return (
            "Radiological convention (left hemisphere shown on the image's RIGHT). "
            "nilearn's annotate=True stamps L/R — verify it matches your convention; "
            "if not, your data/affine is the wrong handedness, do not just relabel."
        )
    return (
        "Neurological convention (left hemisphere shown on the image's LEFT). "
        "annotate=True stamps L/R from the affine — confirm it before submission."
    )


def render_snippet(
    text: str,
    *,
    style: StyleSpec | None = None,
    data_kind: DataKind = DataKind.SIGNED,
    orientation: str = "neurological",
    image: str = "stat_map.nii.gz",
    threshold: float = 3.1,
) -> RenderHandoff:
    """Build a standards-baked render snippet for the tool implied by ``text``."""
    style = style or StyleSpec()
    kind = choose_render_kind(text)
    cmap, symmetric = _CMAP.get(data_kind, ("vik", True))
    w_in, h_in = _figsize_in(style)
    dpi = style.preset.raster_dpi
    notes = [
        _orientation_note(orientation),
        f"Colormap {cmap} (Crameri, perceptually uniform) chosen for data_kind={data_kind}; "
        f"symmetric_cbar={'on' if symmetric else 'off'} so the zero point is not visually shifted.",
        f"Figure sized to {style.preset.double_col_mm:g} mm (double column) at {dpi} dpi for "
        f"{style.journal}; drop to single column ({style.preset.single_col_mm:g} mm) if it fits.",
        "Keep the SVG/PDF vector where the tool allows; export the volume render itself at the "
        "DPI above (it is genuinely raster — that is expected for voxel data).",
    ]
    builder = {
        RenderKind.GLASS_BRAIN: _glass_brain,
        RenderKind.STAT_MAP: _stat_map,
        RenderKind.CONNECTOME: _connectome,
        RenderKind.SURFACE: _surface,
        RenderKind.TRACTOGRAPHY: _tractography,
    }[kind]
    tool, code = builder(image, cmap, symmetric, threshold, w_in, h_in, dpi)
    return RenderHandoff(kind=kind, tool=tool, code=code, notes=notes)


# --------------------------------------------------------------------------- #
# per-kind code templates (nilearn / Surf Ice), with the standards baked in
# --------------------------------------------------------------------------- #
def _header(cmap: str) -> str:
    return (
        "import matplotlib.pyplot as plt\n"
        "from cmcrameri import cm  # Crameri perceptually-uniform colormaps\n"
        "from nilearn import plotting\n\n"
        f"CMAP = cm.{cmap}\n"
    )


def _stat_map(image, cmap, symmetric, threshold, w_in, h_in, dpi) -> tuple[str, str]:
    code = (
        _header(cmap)
        + f'fig = plt.figure(figsize=({w_in}, {h_in}))\n'
        + "disp = plotting.plot_stat_map(\n"
        + f'    "{image}",\n'
        + "    display_mode=\"ortho\",   # add cut_coords=(x, y, z) to pin the slice\n"
        + "    cmap=CMAP,\n"
        + f"    symmetric_cbar={symmetric},\n"
        + f"    threshold={threshold},   # your cluster-forming threshold\n"
        + "    colorbar=True,\n"
        + "    annotate=True,           # stamps L/R + coordinates\n"
        + "    black_bg=False,\n"
        + "    figure=fig,\n"
        + ")\n"
        + f'fig.savefig("figure_statmap.png", dpi={dpi}, bbox_inches="tight")\n'
    )
    return "nilearn", code


def _glass_brain(image, cmap, symmetric, threshold, w_in, h_in, dpi) -> tuple[str, str]:
    code = (
        _header(cmap)
        + f'fig = plt.figure(figsize=({w_in}, {h_in}))\n'
        + "disp = plotting.plot_glass_brain(\n"
        + f'    "{image}",\n'
        + "    display_mode=\"lyrz\",    # sagittal L/R + coronal + axial; labels hemispheres\n"
        + "    cmap=CMAP,\n"
        + "    plot_abs=False,          # keep the sign — do NOT fold negatives onto positives\n"
        + f"    symmetric_cbar={symmetric},\n"
        + f"    threshold={threshold},\n"
        + "    colorbar=True,\n"
        + "    annotate=True,           # stamps L/R\n"
        + "    figure=fig,\n"
        + ")\n"
        + f'fig.savefig("figure_glassbrain.png", dpi={dpi}, bbox_inches="tight")\n'
    )
    return "nilearn", code


def _connectome(image, cmap, symmetric, threshold, w_in, h_in, dpi) -> tuple[str, str]:
    code = (
        _header(cmap)
        + "import numpy as np\n\n"
        + "adjacency = np.load(\"connectivity.npy\")   # n_nodes x n_nodes\n"
        + "coords = np.load(\"node_coords.npy\")       # n_nodes x 3 (MNI mm)\n"
        + f'fig = plt.figure(figsize=({w_in}, {h_in}))\n'
        + "disp = plotting.plot_connectome(\n"
        + "    adjacency, coords,\n"
        + "    edge_cmap=CMAP,\n"
        + "    edge_threshold=\"99%\",   # show the strongest edges only\n"
        + "    display_mode=\"lyrz\",\n"
        + "    colorbar=True,\n"
        + "    figure=fig,\n"
        + ")\n"
        + f'fig.savefig("figure_connectome.png", dpi={dpi}, bbox_inches="tight")\n'
    )
    return "nilearn", code


def _surface(image, cmap, symmetric, threshold, w_in, h_in, dpi) -> tuple[str, str]:
    code = (
        _header(cmap)
        + "from nilearn import datasets\n\n"
        + "fsavg = datasets.fetch_surf_fsaverage()  # or your own *.gii surfaces\n"
        + "for hemi, mesh, bg in ((\"left\", fsavg.infl_left, fsavg.sulc_left),\n"
        + "                       (\"right\", fsavg.infl_right, fsavg.sulc_right)):\n"
        + "    for view in (\"lateral\", \"medial\"):\n"
        + "        disp = plotting.plot_surf_stat_map(\n"
        + "            mesh, stat_map=f\"{hemi}_stat.gii\", hemi=hemi, view=view,\n"
        + "            bg_map=bg, cmap=CMAP, colorbar=True,\n"
        + f"            symmetric_cbar={symmetric}, threshold={threshold},\n"
        + f"            figsize=({round(w_in/2, 2)}, {h_in}),\n"
        + "        )\n"
        + f'        disp.savefig(f"figure_surf_{{hemi}}_{{view}}.png", dpi={dpi})\n'
    )
    return "nilearn", code


def _tractography(image, cmap, symmetric, threshold, w_in, h_in, dpi) -> tuple[str, str]:
    # Surf Ice (scriptable, vector-quality screenshots) is the practical tool for streamlines.
    code = (
        "# Run inside Surf Ice's Scripting > Python console (gl is the Surf Ice module).\n"
        "import gl\n"
        "gl.resetdefaults()\n"
        "gl.meshload('BrainMesh_ICBM152.mz3')   # standard-space cortical mesh\n"
        "gl.meshcurv()                          # subtle curvature shading, not a hard shadow\n"
        "gl.overlayload('streamlines.tck')      # or .trk / .vtk\n"
        "# Crameri 'vik' CLUT keeps direction/scalar coding perceptually uniform:\n"
        "gl.overlaycolorname(1, 'vik')   # install Crameri CLUTs into Surf Ice/lut if missing\n"
        "gl.overlayminmax(1, 0, 1)\n"
        "gl.colorbarvisible(1)\n"
        f"gl.savebmpxy('figure_tracts.png', {int(w_in * dpi)}, {int(h_in * dpi)})\n"
    )
    return "Surf Ice", code
