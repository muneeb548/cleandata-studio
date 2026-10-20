"""Talks to a language model and returns JSON that matches a schema.

Two providers, chosen with AI_PROVIDER in backend/.env:

* ``ollama``    – a model running on this computer through Ollama (https://ollama.com).
                  Free, works offline, and the data never leaves the machine.
* ``anthropic`` – the Claude API. Paid, runs in Anthropic's cloud, so the app asks the
                  user to agree before anything is sent.

Only the Python standard library is used (urllib), so no extra package is needed.
The model never runs code: it only fills in a JSON schema, and the caller checks every
value before the app does anything with it. Prompts and answers are never logged,
because they can contain values from the user's file.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.core.errors import AppError

log = logging.getLogger("cleandata.ai")

DEFAULT_MODELS = {"ollama": "qwen2.5:3b", "anthropic": "claude-haiku-5-5"}
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class LLMClient(Protocol):
    provider: str
    model: str

    def complete_json(self, system: str, prompt: str, schema: dict, max_tokens: int = 2000) -> dict: ...


@dataclass(frozen=True)
class ProviderInfo:
    provider: str          # off | ollama | anthropic
    model: str
    local: bool            # True when the data stays on this computer
    label: str             # shown to the user


def provider_info() -> ProviderInfo:
    provider = settings.ai_provider
    model = settings.ai_model or DEFAULT_MODELS.get(provider, "")
    if provider == "ollama":
        return ProviderInfo("ollama", model, True, f"Local AI ({model} via Ollama, runs on this computer)")
    if provider == "anthropic":
        return ProviderInfo("anthropic", model, False, f"Claude API ({model}, Anthropic cloud)")
    return ProviderInfo("off", "", True, "AI is turned off")


def _unavailable(message: str, hint: str) -> AppError:
    return AppError("ai_unavailable", message, hint, status=503)


def _post_json(url: str, body: dict, headers: dict[str, str], timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed, configured URLs only
        return json.loads(resp.read().decode("utf-8"))


def _parse(text: str) -> dict:
    """The model's answer as a dict. Tolerates a ```json fence that some local models add."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError("ai_bad_answer", "The AI's answer could not be read.",
                       "Try again, or write the request more simply.", status=502) from exc
    if not isinstance(value, dict):
        raise AppError("ai_bad_answer", "The AI's answer could not be read.", "Try again.", status=502)
    return value


class OllamaClient:
    provider = "ollama"

    def __init__(self, model: str, url: str, timeout: float):
        self.model, self.url, self.timeout = model, url, timeout

    def complete_json(self, system: str, prompt: str, schema: dict, max_tokens: int = 2000) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,  # Ollama constrains the answer to this JSON schema
            "options": {"temperature": 0, "num_ctx": 8192, "num_predict": max_tokens},
        }
        try:
            data = _post_json(f"{self.url}/api/chat", body, {}, self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _unavailable(f'The AI model "{self.model}" is not installed.',
                                   f"Open PowerShell and run: ollama pull {self.model}") from exc
            log.warning("ollama error: HTTP %s", exc.code)
            raise _unavailable("The local AI returned an error.", "Restart Ollama and try again.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError) or isinstance(exc, TimeoutError):
                raise _unavailable("The local AI took too long to answer.",
                                   "Try a shorter request, or a smaller model (AI_MODEL in backend/.env).") from exc
            raise _unavailable("The local AI (Ollama) is not running.",
                               "Install Ollama from ollama.com, open it, then try again.") from exc
        return _parse((data.get("message") or {}).get("content", ""))

    def installed(self) -> bool | None:
        """True/False when Ollama answers, None when it is not running."""
        try:
            req = urllib.request.Request(f"{self.url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:  # noqa: S310
                names = [m.get("name", "") for m in json.loads(resp.read().decode("utf-8")).get("models", [])]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        return wanted in names


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str, api_key: str, timeout: float):
        self.model, self.api_key, self.timeout = model, api_key, timeout

    def complete_json(self, system: str, prompt: str, schema: dict, max_tokens: int = 2000) -> dict:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            # Structured outputs: the answer is guaranteed to match the schema.
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        try:
            data = _post_json(ANTHROPIC_URL, body, headers, self.timeout)
        except urllib.error.HTTPError as exc:
            log.warning("anthropic error: HTTP %s", exc.code)
            hints = {401: "Check ANTHROPIC_API_KEY in backend/.env.",
                     402: "Add credit to your Anthropic account.",
                     429: "Too many AI requests. Wait a minute and try again."}
            raise _unavailable("The Claude API refused the request.", hints.get(exc.code, "Try again later.")) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise _unavailable("Could not reach the Claude API.", "Check the internet connection and try again.") from exc
        if data.get("stop_reason") == "max_tokens":
            raise AppError("ai_bad_answer", "The AI's answer was too long.", "Ask for fewer changes at once.", status=502)
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return _parse(text)


def get_client() -> LLMClient:
    """The configured client. Tests replace this function with a fake."""
    info = provider_info()
    if info.provider == "ollama":
        return OllamaClient(info.model, settings.ollama_url, settings.ai_timeout_seconds)
    if info.provider == "anthropic":
        if not settings.anthropic_api_key:
            raise _unavailable("The Claude API key is missing.", "Set ANTHROPIC_API_KEY in backend/.env.")
        return AnthropicClient(info.model, settings.anthropic_api_key, settings.ai_timeout_seconds)
    raise _unavailable("The AI assistant is turned off.", "Set AI_PROVIDER=ollama in backend/.env and restart the backend.")
