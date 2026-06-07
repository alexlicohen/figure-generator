"""Thin Anthropic (Claude) client wrapper.

The only network LLM step in the pipeline. Uses structured outputs (`messages.parse`)
for schema extraction — on Opus 4.8 there is no `temperature`/`top_p`/`top_k` and no
`budget_tokens`, so determinism comes from the JSON schema constraint plus a low `effort`
tier rather than sampling parameters. The SDK already retries 429/5xx with exponential
backoff (configurable via `max_retries`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from .config import Config, load_config

if TYPE_CHECKING:  # avoid importing the SDK (and Pydantic generic plumbing) at module load
    from pydantic import BaseModel

T = TypeVar("T", bound="BaseModel")


class LLMError(RuntimeError):
    """Raised for configuration or call failures in the Claude wrapper."""


class LLMClient:
    """Lazily-constructed Claude client with JSON-schema and plain-text helpers."""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load_config()
        self._client = None  # constructed on first use

    # -- internal ---------------------------------------------------------- #
    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.config.anthropic_api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Export it before running extraction:\n"
                "    export ANTHROPIC_API_KEY=sk-ant-..."
            )
        try:
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - import guard
            raise LLMError("The 'anthropic' package is not installed.") from exc

        self._client = anthropic.Anthropic(
            timeout=self.config.http_timeout * 4,  # extraction may produce long output
            max_retries=self.config.http_max_retries,
        )
        return self._client

    # -- public API -------------------------------------------------------- #
    def parse(
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        effort: str | None = None,
    ) -> T:
        """Return a validated instance of ``schema`` from a Claude structured-output call.

        Raises LLMError on refusal, truncation, or a missing parsed result.
        """
        client = self._ensure_client()
        response = client.messages.parse(
            model=self.config.model,
            max_tokens=max_tokens,
            output_config={"effort": effort or self.config.extract_effort},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise LLMError(f"Claude refused the extraction request: {detail}")
        if response.stop_reason == "max_tokens":
            raise LLMError("Extraction truncated (max_tokens); retry with a higher limit.")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise LLMError("Claude returned no parseable structured output.")
        return parsed

    def complete(self, *, system: str, user: str, max_tokens: int = 2048) -> str:
        """Return the concatenated text of a plain Claude completion (e.g. self-check)."""
        client = self._ensure_client()
        response = client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            output_config={"effort": self.config.extract_effort},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
