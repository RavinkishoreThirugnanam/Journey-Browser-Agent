from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Test Automation Journey Mapping Platform"
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"
    jira_base_url: str = ""
    jira_project_key: str = ""
    jira_username: str = ""
    jira_api_token: str = ""
    llm_provider: str = "OpenAI"
    llm_model: str = "gpt-4o-mini"
    llm_api_endpoint: str = ""
    llm_auth_token: str = ""
    openai_base_url: str = ""
    app_url: str = ""
    email: str = ""
    password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
