"""Route a FigureSchema to the generator that handles its figure type."""

from __future__ import annotations

from .generators import Generator
from .generators.anatomical import AnatomicalGenerator
from .generators.circuit import CircuitGenerator
from .generators.pipeline import PipelineGenerator
from .models import FigureType

_GENERATORS: list[Generator] = [
    CircuitGenerator(),
    PipelineGenerator(),
    AnatomicalGenerator(),
]


def route(figure_type: FigureType) -> Generator:
    for gen in _GENERATORS:
        if figure_type in gen.figure_types:
            return gen
    raise ValueError(f"No generator registered for figure type: {figure_type}")
