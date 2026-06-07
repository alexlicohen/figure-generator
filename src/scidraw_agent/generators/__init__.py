"""Generators turn a FigureSchema into SVG. Every output is routed through style_guard
by compose before the manifest is written, so generators only need to *prefer* compliant
output (palette colours, legible fonts) — the guard is the backstop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from ..models import AssetRecord, FigureSchema
from ..palette import PaletteRegistry
from ..theme import StyleSpec

if TYPE_CHECKING:
    from ..fetch import AssetFetcher


@dataclass
class GeneratorResult:
    svg: str
    assets: list[AssetRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Generator(Protocol):
    figure_types: set

    def generate(
        self,
        schema: FigureSchema,
        style: StyleSpec,
        palette: PaletteRegistry,
        *,
        fetcher: AssetFetcher | None = None,
    ) -> GeneratorResult: ...
