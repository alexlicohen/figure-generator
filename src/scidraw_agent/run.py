"""End-to-end orchestration: text/file -> schema -> self-check -> composed figure.

Ties ingest -> extract -> self_check -> compose_figure. Self-check warnings (invented
entities, undeclared brain orientation, dangling edges) are surfaced in the manifest.
NeuroDeclineError from the extractor propagates to the caller (CLI/MCP) for the redirect.
"""

from __future__ import annotations

from pathlib import Path

from .compose import compose_figure
from .config import Config, load_config
from .extract import extract
from .ingest import ingest
from .models import Manifest
from .selfcheck import self_check
from .theme import StyleSpec


def figure_from_text(
    text: str,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    llm=None,
    fetcher=None,
    style: StyleSpec | None = None,
    section: str | None = None,
) -> Manifest:
    """Build a figure from free text (or a section thereof)."""
    config = config or load_config()
    source = ingest(text, section=section)
    schema = extract(source, llm=llm, config=config)
    warnings = self_check(source, schema)
    return compose_figure(
        schema, out_dir, config=config, style=style, fetcher=fetcher, extra_warnings=warnings
    )


def figure_from_file(
    path: str | Path,
    out_dir: str | Path,
    *,
    config: Config | None = None,
    llm=None,
    fetcher=None,
    style: StyleSpec | None = None,
    section: str | None = None,
) -> Manifest:
    """Build a figure from a .pdf / .txt / .md file (optionally a named section)."""
    config = config or load_config()
    text = ingest(Path(path), section=section)
    schema = extract(text, llm=llm, config=config)
    warnings = self_check(text, schema)
    return compose_figure(
        schema, out_dir, config=config, style=style, fetcher=fetcher, extra_warnings=warnings
    )
