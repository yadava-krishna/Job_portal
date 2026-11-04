"""LLM provider abstraction.

Providers:
  * anthropic          -- official Anthropic SDK, structured JSON output.
  * openai_compatible  -- any /chat/completions endpoint (e.g. a local Ollama container).
  * rule_based         -- no LLM; callers use their deterministic scorers.

`build_llm` returns None for rule_based, or when the provider is unusable and
`fallback_to_rule_based` is enabled; the reason is returned so callers can label
every result with how it was produced.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from core.settings import LLMConfig, LLMProvider

log = logging.getLogger(__name__)


class LLMError(Exception):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class LLMClient(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int = 16000) -> dict[str, Any]:
        ...


class AnthropicClient:
    def __init__(self, cfg: LLMConfig, api_key: str | None):
        import anthropic

        self._anthropic = anthropic
        self.cfg = cfg
        self.name = f"anthropic:{cfg.model}"
        self.client = anthropic.Anthropic(api_key=api_key, timeout=cfg.timeout_seconds, max_retries=3)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int = 16000) -> dict[str, Any]:
        a = self._anthropic
        try:
            # Server-side fallback re-runs a declined request on Anthropic's recommended
            # fallback model instead of returning a refusal.
            response = self.client.beta.messages.create(
                model=self.cfg.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.cfg.effort, "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.RateLimitError as exc:
            raise LLMError(f"Anthropic rate limit: {exc.message}", transient=True) from exc
        except a.AuthenticationError as exc:
            raise LLMError("Anthropic authentication failed - check the API key in .env") from exc
        except a.BadRequestError as exc:
            raise LLMError(f"Anthropic rejected the request: {exc.message}") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}", transient=exc.status_code >= 500) from exc
        except (a.APIConnectionError, a.APITimeoutError) as exc:
            raise LLMError(f"Anthropic connection error: {exc}", transient=True) from exc

        if response.stop_reason == "refusal":
            raise LLMError("Model declined the request (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("Model output was truncated (max_tokens)", transient=True)
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise LLMError("Model returned no text output")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON: {exc}") from exc


class OpenAICompatibleClient:
    """Minimal client for OpenAI-style /chat/completions endpoints (not used for Claude)."""

    def __init__(self, cfg: LLMConfig, api_key: str | None):
        import httpx

        if not cfg.base_url:
            raise LLMError("llm.base_url is required for the openai_compatible provider")
        self.cfg = cfg
        self.name = f"openai_compatible:{cfg.model}"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._httpx = httpx
        self.http = httpx.Client(base_url=cfg.base_url.rstrip("/"), headers=headers, timeout=cfg.timeout_seconds)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], *, max_tokens: int = 16000) -> dict[str, Any]:
        payload = {
            "model": self.cfg.model,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + "\n\nRespond with a single JSON object matching this JSON Schema:\n" + json.dumps(schema)},
                {"role": "user", "content": user},
            ],
        }
        try:
            r = self.http.post("/chat/completions", json=payload)
        except self._httpx.HTTPError as exc:
            raise LLMError(f"LLM endpoint unreachable: {exc}", transient=True) from exc
        if r.status_code >= 400:
            raise LLMError(f"LLM endpoint returned HTTP {r.status_code}", transient=r.status_code in (408, 429) or r.status_code >= 500)
        try:
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response: {exc}") from exc


def build_llm(cfg: LLMConfig) -> tuple[LLMClient | None, str]:
    """Return (client, description). client is None when rule-based scoring must be used."""
    if cfg.provider == LLMProvider.RULE_BASED:
        return None, "rule_based (configured)"

    api_key = os.environ.get(cfg.api_key_env) or None
    try:
        if cfg.provider == LLMProvider.ANTHROPIC:
            if not api_key and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
                raise LLMError(f"{cfg.api_key_env} is not set")
            client: LLMClient = AnthropicClient(cfg, api_key)
        else:
            client = OpenAICompatibleClient(cfg, api_key)
    except (LLMError, ImportError) as exc:
        if cfg.fallback_to_rule_based:
            log.warning("LLM provider %s unavailable (%s); using the rule-based scorer.", cfg.provider, exc)
            return None, f"rule_based (LLM unavailable: {exc})"
        raise LLMError(f"LLM provider {cfg.provider} unavailable: {exc}") from exc
    return client, client.name
