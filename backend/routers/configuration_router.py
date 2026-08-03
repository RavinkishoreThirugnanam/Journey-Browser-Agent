import json
import os
from copy import deepcopy
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from core.config import STORAGE_DIR
from schemas.configuration_schema import Configuration, ConfigurationSaveResponse, JiraConnectionResponse, LLMConnectionResponse
from services.jira_client_service import JiraClientError, test_connection
from services.llm_generation_service import LLMGenerationError, generate_json_with_openai, runtime_config_from_llm

router = APIRouter()
CONFIG_FILE = STORAGE_DIR / "configurations.json"
LEGACY_CONFIG_FILE = STORAGE_DIR / "configuration.json"
_CONFIG_LOCK = RLock()

DEFAULT_CONFIGURATION = {
    "jira": {"base_url": "", "project_key": "", "username": "", "api_token": "", "auth_type": "basic", "issue_type": "Story", "test_case_issue_type": "Test"},
    "llm": {"provider": "OpenAI", "model": "gpt-4o-mini", "supervisor_model": "gpt-4o-mini", "api_endpoint": "", "auth_token": "", "temperature": 0.2, "browser_timeout_screenshot": 30.0, "browser_timeout_navigate": 30.0, "browser_use_enabled": True, "browser_use_cdp_url": "http://localhost:9222", "browser_use_max_steps": 25, "browser_use_vision": True, "supervisor_enabled": True, "browser_agent_prompt": ""},
    "application": {"base_url": "", "environment": "development", "default_project": "", "global_parameters": {}, "browser_headers": {}, "default_follow_links": True},
}

MODEL_CATALOG = [
    {"provider": "OpenAI", "model": "gpt-4o-mini", "label": "GPT-4o mini"},
    {"provider": "OpenAI", "model": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
    {"provider": "OpenAI", "model": "gpt-4.1", "label": "GPT-4.1"},
    {"provider": "OpenAI", "model": "gpt-5", "label": "GPT-5"},
    {"provider": "Google Gemini", "model": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
    {"provider": "Google Gemini", "model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
]


def _normalise_configuration(data) -> dict:
    payload = data if isinstance(data, dict) else {}
    return {
        "jira": {**DEFAULT_CONFIGURATION["jira"], **(payload.get("jira") or {})},
        "llm": {**DEFAULT_CONFIGURATION["llm"], **(payload.get("llm") or {})},
        "application": {**DEFAULT_CONFIGURATION["application"], **(payload.get("application") or {})},
    }


def _read_unlocked() -> dict:
    source = CONFIG_FILE if CONFIG_FILE.exists() else LEGACY_CONFIG_FILE if LEGACY_CONFIG_FILE.exists() else None
    if source is None:
        return deepcopy(DEFAULT_CONFIGURATION)
    try:
        raw = source.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        return deepcopy(DEFAULT_CONFIGURATION)
    normalized = _normalise_configuration(data)
    if source == LEGACY_CONFIG_FILE:
        _write_unlocked(normalized)
    return normalized


def _write_unlocked(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = CONFIG_FILE.with_name(f".{CONFIG_FILE.name}.{uuid4().hex}.tmp")
    try:
        with temp_file.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_file, CONFIG_FILE)
    finally:
        temp_file.unlink(missing_ok=True)


def _read() -> dict:
    with _CONFIG_LOCK:
        return _read_unlocked()


def _write(data: dict) -> dict:
    with _CONFIG_LOCK:
        normalized = _normalise_configuration(data)
        _write_unlocked(normalized)
        persisted = _read_unlocked()
        if persisted != normalized:
            raise OSError("Configuration verification failed after save")
        return persisted

@router.get("/configuration", response_model=Configuration)
def get_configuration():
    return _read()


@router.get("/configuration/llm-models")
def get_llm_models():
    return {"models": MODEL_CATALOG}


@router.post("/configuration", response_model=ConfigurationSaveResponse)
def save_configuration(payload: Configuration):
    data = _write(payload.model_dump())
    return {"message": "Configuration saved", "configuration": data}


@router.post("/configuration/test-jira", response_model=JiraConnectionResponse)
def test_jira_connection(payload: Configuration):
    try:
        details = test_connection(payload.jira)
        return {"connected": True, "message": "Jira connection successful", "details": details}
    except JiraClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Jira validation failed: {exc}') from exc


@router.post("/configuration/test-llm", response_model=LLMConnectionResponse)
def test_llm_connection(payload: Configuration):
    llm = payload.llm
    if not llm.model or not llm.provider or not llm.auth_token:
        raise HTTPException(status_code=400, detail="LLM provider, model, and auth token are required")
    provider = (llm.provider or "").strip()
    model = (llm.model or "").strip()
    runtime = runtime_config_from_llm(llm)
    try:
        generate_json_with_openai(
            "Return a JSON object with the key status and value ok.",
            {"purpose": "connection_test"},
            response_contract='{"status":"ok"}',
            timeout=30,
            runtime_config=runtime,
        )
        return {"connected": True, "message": f"{provider} connection successful", "details": {"provider": provider, "model": model}}
    except LLMGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc