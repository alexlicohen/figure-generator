"""Runtime configuration: env-driven, no hardcoded secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default Claude model. Opus 4.8 removes temperature/top_p/top_k and budget_tokens;
# determinism for extraction comes from structured outputs + low effort, not sampling params.
DEFAULT_MODEL = "claude-opus-4-8"

# Effort tier for the (deterministic-as-possible) extraction call. low = fewer tokens,
# tighter scoping — appropriate for schema extraction where we want predictability.
DEFAULT_EXTRACT_EFFORT = "low"

# Network defaults applied to every outbound HTTP call (Zenodo, asset backends).
HTTP_TIMEOUT_SECONDS = 30.0
HTTP_MAX_RETRIES = 4

# A descriptive User-Agent is REQUIRED for Zenodo — default request agents get HTTP 403.
USER_AGENT = "scidraw-agent/0.1 (+https://github.com/alexlicohen/figure-generator)"


def _default_cache_dir() -> Path:
    override = os.environ.get("SCIDRAW_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "scidraw-agent"


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration resolved from the environment."""

    model: str = field(default_factory=lambda: os.environ.get("SCIDRAW_MODEL", DEFAULT_MODEL))
    extract_effort: str = field(
        default_factory=lambda: os.environ.get("SCIDRAW_EXTRACT_EFFORT", DEFAULT_EXTRACT_EFFORT)
    )
    cache_dir: Path = field(default_factory=_default_cache_dir)
    http_timeout: float = HTTP_TIMEOUT_SECONDS
    http_max_retries: int = HTTP_MAX_RETRIES
    user_agent: str = USER_AGENT
    # Default journal preset for export sizing/specs (see theme.py).
    journal: str = field(default_factory=lambda: os.environ.get("SCIDRAW_JOURNAL", "nature"))

    @property
    def assets_dir(self) -> Path:
        return self.cache_dir / "assets"

    @property
    def ledger_path(self) -> Path:
        return self.cache_dir / "ledger.json"

    def ensure_dirs(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    @property
    def anthropic_api_key(self) -> str | None:
        """Read the API key from the environment; never stored in the dataclass."""
        return os.environ.get("ANTHROPIC_API_KEY")


def load_config() -> Config:
    """Return a Config resolved from the current environment."""
    return Config()
