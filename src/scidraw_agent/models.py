"""Core data contracts (the owned intermediate representation) plus manifest models.

FigureSchema is the JSON IR Claude produces from a prompt or ingested text. Everything
downstream (router, generators, compose) consumes these models, and the manifest records
both license provenance (per asset) and standards provenance (applied fixes / overrides /
warnings) for the figure legend and reproducibility.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class FigureType(StrEnum):
    MECHANISTIC_CIRCUIT = "mechanistic_circuit"
    ANALYSIS_PIPELINE = "analysis_pipeline"
    STUDY_DESIGN = "study_design"
    ANATOMICAL = "anatomical"
    DATA_PLOT = "data_plot"


class EntityKind(StrEnum):
    REGION = "region"
    CELLTYPE = "celltype"
    MODALITY = "modality"
    COHORT = "cohort"
    STEP = "step"
    OTHER = "other"


class EdgeRelation(StrEnum):
    PROJECTS_TO = "projects_to"
    INHIBITS = "inhibits"
    EXCITES = "excites"
    MODULATES = "modulates"
    PREDICTS = "predicts"
    FLOWS_TO = "flows_to"
    OTHER = "other"


# Excitatory vs inhibitory drives arrowhead semantics in the generators
# (filled pointed head = excitatory/projection, flat T-bar = inhibitory, dashed/open =
# modulatory). Centralised here so extract.py and the circuit generator agree.
EXCITATORY_RELATIONS = {EdgeRelation.PROJECTS_TO, EdgeRelation.EXCITES, EdgeRelation.FLOWS_TO}
INHIBITORY_RELATIONS = {EdgeRelation.INHIBITS}
MODULATORY_RELATIONS = {EdgeRelation.MODULATES}


class DataKind(StrEnum):
    """How a quantity maps to colour — drives colormap selection in palette.py."""

    NONE = "none"
    CATEGORICAL = "categorical"
    MAGNITUDE = "magnitude"  # unsigned/one-sided -> sequential (batlow/viridis)
    SIGNED = "signed"  # centred at zero (t/z-maps, %change) -> diverging (vik)
    CYCLIC = "cyclic"  # phase/angle -> cyclic (vikO)


# --------------------------------------------------------------------------- #
# Figure schema (the IR)
# --------------------------------------------------------------------------- #
class Entity(BaseModel):
    id: str = Field(..., description="Stable identifier referenced by edges.")
    label: str = Field(..., description="Human-readable label shown in the figure.")
    kind: EntityKind = EntityKind.OTHER
    suggested_asset_query: str | None = Field(
        default=None,
        description="Search term for the asset layer (e.g. 'pyramidal neuron').",
    )
    group: str | None = Field(
        default=None,
        description="Group/cohort name for stable colour+shape mapping across panels.",
    )


class Edge(BaseModel):
    source: str = Field(..., description="Entity id.")
    target: str = Field(..., description="Entity id.")
    relation: EdgeRelation = EdgeRelation.OTHER
    label: str | None = None


class FigureSchema(BaseModel):
    """The structured figure description Claude emits and generators consume."""

    figure_type: FigureType
    entities: list[Entity] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    data_kind: DataKind = DataKind.NONE
    notes: str = ""
    caption_seed: str = ""

    def entity_ids(self) -> set[str]:
        return {e.id for e in self.entities}

    def dangling_edges(self) -> list[Edge]:
        """Edges whose endpoints are not declared entities (validation aid)."""
        ids = self.entity_ids()
        return [e for e in self.edges if e.source not in ids or e.target not in ids]


# --------------------------------------------------------------------------- #
# Data-plot request (M8 data_plot module)
# --------------------------------------------------------------------------- #
class PlotRequest(BaseModel):
    """A distribution-plot request: one list of values per group.

    ``replicates`` (optional, parallel to each group's values) enables a SuperPlot —
    points coloured by replicate, replicate means overlaid, stats on N replicates.
    """

    groups: dict[str, list[float]]
    replicates: dict[str, list[str]] | None = None
    xlabel: str = ""
    ylabel: str = "value"
    title: str = ""
    # force a plot kind to exercise the dynamite ban; "auto" picks by sample size
    force_kind: str = "auto"


# --------------------------------------------------------------------------- #
# Graphical abstract (structural composition — no image models)
# --------------------------------------------------------------------------- #
class GAStep(BaseModel):
    """A numbered step inside a track."""

    head: str
    detail: str = ""


class GAImage(BaseModel):
    """An image slot. A real render (``path``, PNG/SVG) is preferred and NEVER generated; a
    CC ``asset_query`` is the fallback; absent both, a labelled placeholder is drawn."""

    path: str | None = None
    asset_query: str | None = None
    caption: str = ""


class GAItem(BaseModel):
    """One element in a section row: a titled card, an image, a track, or an image grid."""

    kind: str = "card"  # "card" | "image" | "track" | "grid"
    title: str = ""
    lines: list[str] = Field(default_factory=list)
    steps: list[GAStep] = Field(default_factory=list)
    image: GAImage | None = None  # single image slot (kind="card"/"image")
    images: list[GAImage] = Field(default_factory=list)  # montage cells (kind="grid")
    grid_cols: int | None = None  # explicit grid columns; else chosen by count
    icon: str | None = None  # Health-Icons name/query, drawn small in the accent colour
    accent: str | None = None  # explicit accent; else cycles the house palette
    weight: float = 1.0  # relative width within the row


class GARow(BaseModel):
    """A left-to-right row of items joined by an optional connector."""

    items: list[GAItem] = Field(default_factory=list)
    connector: str = "none"  # between items: "arrow" | "plus" | "none"


class GASection(BaseModel):
    """A titled band of one or more stacked rows.

    Either set ``rows`` (multi-row), or use ``items`` + ``connector`` as a single-row shorthand.
    """

    title: str
    items: list[GAItem] = Field(default_factory=list)
    connector: str = "none"
    rows: list[GARow] = Field(default_factory=list)

    def as_rows(self) -> list[GARow]:
        return self.rows or [GARow(items=self.items, connector=self.connector)]


class GraphicalAbstract(BaseModel):
    """A structural grant graphical abstract: stacked titled sections of cards/images/tracks.

    The design (bands, cards, tracks, connectors, colour system) is generated; images are
    slotted from real renders or CC assets — never image-model output.
    """

    title: str = ""
    sections: list[GASection] = Field(default_factory=list)
    caption_seed: str = ""
    # Column width: "full" | "half" | "third" of the page (figures are rarely full width).
    # Narrow widths reflow multi-item rows to stack vertically. ``width`` is an explicit px
    # override if set (>0); otherwise ``column`` chooses it.
    column: str = "half"
    width: float = 0.0


# --------------------------------------------------------------------------- #
# Asset provenance
# --------------------------------------------------------------------------- #
class AssetRecord(BaseModel):
    """One imported organic asset, with the licensing trail for the legend."""

    query: str
    title: str
    backend: str = Field(..., description="Source backend, e.g. 'zenodo'.")
    doi: str | None = None
    license: str | None = Field(
        default=None, description="SPDX/Zenodo license id, e.g. 'cc-by-4.0'."
    )
    source_url: str | None = None
    local_path: str | None = Field(default=None, description="Cached SVG path.")
    creators: list[str] = Field(default_factory=list)
    is_placeholder: bool = Field(
        default=False,
        description="True when no asset was found and a labelled box was substituted.",
    )


# --------------------------------------------------------------------------- #
# Standards provenance
# --------------------------------------------------------------------------- #
class StandardsTier(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    DEFAULT = "default"


class StandardsAction(BaseModel):
    """A single design-standards event applied to or flagged on a figure."""

    rule_id: str
    tier: StandardsTier
    message: str
    auto_fixed: bool = False
    source_url: str | None = None


class StandardsReport(BaseModel):
    applied_fixes: list[StandardsAction] = Field(default_factory=list)
    warnings: list[StandardsAction] = Field(default_factory=list)
    overrides: list[StandardsAction] = Field(default_factory=list)

    def add(self, action: StandardsAction) -> None:
        if action.tier is StandardsTier.WARN:
            self.warnings.append(action)
        elif action.auto_fixed or action.tier is StandardsTier.DEFAULT:
            self.applied_fixes.append(action)
        else:
            self.overrides.append(action)


# --------------------------------------------------------------------------- #
# Attribution / credits
# --------------------------------------------------------------------------- #
class Credits(BaseModel):
    """Paste-ready attribution for the figure (also written to figure.credits.txt).

    Reused image assets are credited in the figure legend, not the bibliography.
    """

    legend_line: str = Field(
        default="", description="Compact credit line (grouped by source+license) — paste this."
    )
    legend_line_full: str = Field(
        default="", description="Full Title/Author/Source/License (CC TASL) credit line."
    )
    per_asset: list[str] = Field(default_factory=list)
    attribution_required: bool = Field(
        default=False, description="True if any asset is CC-BY (legally must be credited)."
    )


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
class Manifest(BaseModel):
    """Per-figure record emitted alongside the SVG (figure.manifest.json)."""

    figure_type: FigureType
    caption_seed: str = ""
    svg_path: str | None = None
    raster_paths: list[str] = Field(default_factory=list)
    journal: str = "nature"
    assets: list[AssetRecord] = Field(default_factory=list)
    standards: StandardsReport = Field(default_factory=StandardsReport)
    credits: Credits = Field(default_factory=Credits)
    warnings: list[str] = Field(
        default_factory=list,
        description="Free-form figure-level warnings (e.g. missing-asset placeholders).",
    )
