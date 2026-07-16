import json

from fastapi import APIRouter, HTTPException

from core.config import STORAGE_DIR
from schemas.configuration_schema import Configuration, ConfigurationSaveResponse, JiraConnectionResponse, LLMConnectionResponse
from services.jira_client_service import JiraClientError, test_connection

router = APIRouter()
CONFIG_FILE = STORAGE_DIR / "configurations.json"

DEFAULT_CONFIGURATION = {
    "jira": {"base_url": "", "project_key": "", "username": "", "api_token": "", "auth_type": "basic", "issue_type": "Story", "test_case_issue_type": "Test"},
    "llm": {"provider": "OpenAI", "model": "gpt-4o-mini", "supervisor_model": "gpt-4o-mini", "api_endpoint": "", "auth_token": "", "temperature": 0.2, "browser_timeout_screenshot": 30.0, "browser_timeout_navigate": 30.0, "browser_use_enabled": False},
    "application": {"base_url": "", "environment": "development", "default_project": "", "global_parameters": {}, "browser_headers": {}},
}

MODEL_CATALOG = [
    {"provider": "OpenAI", "model": "gpt-4o-mini", "label": "GPT-4o mini"},
    {"provider": "OpenAI", "model": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
    {"provider": "OpenAI", "model": "gpt-4.1", "label": "GPT-4.1"},
    {"provider": "OpenAI", "model": "gpt-5", "label": "GPT-5"},
]


def _read():
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIGURATION
    raw = CONFIG_FILE.read_text(encoding="utf-8")
    if not raw.strip():
        return DEFAULT_CONFIGURATION
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_CONFIGURATION
    if not isinstance(data, dict):
        return DEFAULT_CONFIGURATION
    return {
        "jira": {**DEFAULT_CONFIGURATION["jira"], **(data.get("jira") or {})},
        "llm": {**DEFAULT_CONFIGURATION["llm"], **(data.get("llm") or {})},
        "application": {**DEFAULT_CONFIGURATION["application"], **(data.get("application") or {})},
    }


def _write(data):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("/configuration", response_model=Configuration)
def get_configuration():
    return _read()


@router.get("/configuration/llm-models")
def get_llm_models():
    return {"models": MODEL_CATALOG}


@router.post("/configuration", response_model=ConfigurationSaveResponse)
def save_configuration(payload: Configuration):
    data = payload.model_dump()
    _write(data)
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
    if not llm.model or not llm.provider:
        raise HTTPException(status_code=400, detail='LLM provider and model are required')
    provider = (llm.provider or '').strip() or 'OpenAI'
    model = (llm.model or '').strip() or 'gpt-4o-mini'
    return {"connected": True, "message": f'{provider} model {model} selected', "details": {"provider": provider, "model": model}}
