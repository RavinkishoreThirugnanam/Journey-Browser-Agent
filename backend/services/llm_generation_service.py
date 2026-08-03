from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import requests

from core.config import STORAGE_DIR

CONFIG_FILE = STORAGE_DIR / "configurations.json"
MAX_PROMPT_CHARS = 72000
MAX_SYSTEM_PROMPT_CHARS = 16000
MAX_CONTRACT_CHARS = 12000
MAX_STRING_CHARS = 2000
MAX_LIST_ITEMS = 80
MAX_OUTPUT_TOKENS = 4096


def _normalize_secret(value: Any) -> str:
    token = str(value or "").strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        token = token[1:-1].strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def _is_placeholder_secret(token: str) -> bool:
    return token.lower() in {"secret", "token", "your-token", "your-api-key", "api-key", "changeme"}
def _compact_value(value: Any, depth: int = 0) -> Any:
    if depth > 6: return "[truncated]"
    if isinstance(value, str): return value if len(value) <= MAX_STRING_CHARS else value[:MAX_STRING_CHARS] + "...[truncated]"
    if isinstance(value, list): return [_compact_value(item, depth + 1) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, dict):
        priority = {"journey_id", "objective", "journey_objective", "starting_url", "source_url", "application_url", "page_url", "page_title", "action", "event", "element", "selector", "role", "tag", "text", "outcome", "summary", "test_case_id", "story_id"}
        keys = sorted(value, key=lambda key: (str(key) not in priority, str(key)))
        return {str(key): _compact_value(value[key], depth + 1) for key in keys}
    return value

def _bounded_json(value: Any, limit: int = MAX_PROMPT_CHARS) -> str:
    encoded = json.dumps(_compact_value(deepcopy(value)), ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= limit: return encoded
    return json.dumps({"_truncated": True, "note": "Browser evidence exceeded the request budget and was compacted.", "evidence_preview": encoded[:4000]}, ensure_ascii=False, separators=(",", ":"))


class LLMGenerationError(RuntimeError):
    """Raised when the configured LLM cannot produce a usable response."""


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    model: str
    api_endpoint: str
    auth_token: str
    temperature: float

    @property
    def enabled(self) -> bool:
        return self.provider.lower() in {"openai", "google gemini", "gemini", "google"} and bool(self.model and self.auth_token)


def _read_configuration() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def get_llm_runtime_config() -> LLMRuntimeConfig:
    config = _read_configuration()
    llm = config.get("llm", {}) if isinstance(config, dict) else {}
    provider = str(llm.get("provider") or os.environ.get("LLM_PROVIDER") or "OpenAI").strip()
    model = str(llm.get("model") or os.environ.get("OPENAI_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4o-mini").strip()
    api_endpoint = str(
        llm.get("api_endpoint")
        or os.environ.get("OPENAI_API_ENDPOINT")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
        or "https://api.openai.com/v1/chat/completions"
    ).strip()
    auth_token = str(
        llm.get("auth_token")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_TOKEN")
        or os.environ.get("OPENAI_AUTH_TOKEN")
        or os.environ.get("LLM_AUTH_TOKEN")
        or ""
    ).strip()
    auth_token = _normalize_secret(auth_token)
    if _is_placeholder_secret(auth_token):
        auth_token = ''
    try:
        temperature = float(llm.get("temperature", 0.2))
    except (TypeError, ValueError):
        temperature = 0.2
    return LLMRuntimeConfig(provider=provider, model=model, api_endpoint=_chat_completions_url(api_endpoint), auth_token=auth_token, temperature=temperature)


def _chat_completions_url(endpoint: str) -> str:
    endpoint = (endpoint or "https://api.openai.com/v1/chat/completions").rstrip("/")
    if endpoint.endswith("/chat/completions"):
        return endpoint
    if endpoint.endswith("/v1"):
        return f"{endpoint}/chat/completions"
    if endpoint.endswith("/v1/"):
        return f"{endpoint}chat/completions"
    return endpoint


def runtime_config_from_llm(value: Any) -> LLMRuntimeConfig:
    data = value.model_dump() if hasattr(value, "model_dump") else dict(value or {})
    provider = str(data.get("provider") or "OpenAI").strip()
    model = str(data.get("model") or "gpt-4o-mini").strip()
    default_endpoint = "https://generativelanguage.googleapis.com/v1beta" if provider.lower() in {"google gemini", "gemini", "google"} else "https://api.openai.com/v1/chat/completions"
    api_endpoint = str(data.get("api_endpoint") or default_endpoint).strip()
    auth_token = _normalize_secret(data.get("auth_token"))
    if _is_placeholder_secret(auth_token):
        auth_token = ""
    try:
        temperature = float(data.get("temperature", 0.2))
    except (TypeError, ValueError):
        temperature = 0.2
    return LLMRuntimeConfig(provider=provider, model=model, api_endpoint=_chat_completions_url(api_endpoint), auth_token=auth_token, temperature=temperature)


def is_llm_enabled() -> bool:
    return get_llm_runtime_config().enabled


def generate_json_with_openai(system_prompt: str, user_payload: dict[str, Any], *, response_contract: str, timeout: int = 90, runtime_config: LLMRuntimeConfig | None = None) -> dict[str, Any]:
    runtime = runtime_config or get_llm_runtime_config()
    if not runtime.enabled:
        raise LLMGenerationError("OpenAI generation is not configured. Add an OpenAI auth token in Configuration Settings or set OPENAI_API_KEY.")

    if runtime.provider.lower() in {"google gemini", "gemini", "google"}:
        endpoint = runtime.api_endpoint.rstrip("/")
        if endpoint.endswith("/v1/chat/completions"):
            endpoint = "https://generativelanguage.googleapis.com/v1beta"
        if not endpoint.endswith("/v1beta"):
            endpoint = endpoint + "/v1beta"
        url = f"{endpoint}/models/{runtime.model}:generateContent"
        prompt = system_prompt.strip()[:MAX_SYSTEM_PROMPT_CHARS] + "\n\nResponse contract:\n" + response_contract[:MAX_CONTRACT_CHARS] + "\n\nSource payload:\n" + _bounded_json(user_payload)
        try:
            response = requests.post(
                url,
                params={"key": runtime.auth_token},
                headers={"Content-Type": "application/json"},
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": runtime.temperature, "responseMimeType": "application/json", "maxOutputTokens": MAX_OUTPUT_TOKENS}},
                timeout=timeout,
            )
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                    error_message = error_payload.get("error", {}).get("message") or str(error_payload)
                except ValueError:
                    error_message = response.text[:500]
                raise LLMGenerationError(f"Google Gemini rejected the generation request ({response.status_code}): {error_message}")
            data = response.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise LLMGenerationError("Google Gemini response was not a JSON object.")
            return parsed
        except LLMGenerationError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMGenerationError(f"Google Gemini generation failed: {exc}") from exc
    payload = {
        "model": runtime.model,
        "temperature": runtime.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt.strip()[:MAX_SYSTEM_PROMPT_CHARS]},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "response_contract": response_contract[:MAX_CONTRACT_CHARS],
                        "source_payload": json.loads(_bounded_json(user_payload)),
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    payload["max_tokens"] = MAX_OUTPUT_TOKENS
    headers = {
        "Authorization": f"Bearer {runtime.auth_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(runtime.api_endpoint, headers=headers, json=payload, timeout=timeout)
        if response.status_code == 401:
            raise LLMGenerationError("OpenAI authentication failed (401). In Configuration Settings, paste the raw API key only (for example sk-...), without the Bearer prefix, quotes, or extra spaces.")
        if response.status_code >= 400:
            try:
                error_payload = response.json()
                error_message = error_payload.get("error", {}).get("message") or str(error_payload)
            except ValueError:
                error_message = response.text[:500]
            raise LLMGenerationError(f"OpenAI rejected the generation request ({response.status_code}): {error_message}")
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise LLMGenerationError("OpenAI returned an empty response.")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise LLMGenerationError("OpenAI response was not a JSON object.")
        return parsed
    except LLMGenerationError:
        raise
    except requests.RequestException as exc:
        raise LLMGenerationError(f"OpenAI request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LLMGenerationError(f"OpenAI response was not valid JSON: {exc}") from exc





