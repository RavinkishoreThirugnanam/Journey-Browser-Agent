from pydantic import BaseModel, Field


class JiraConfiguration(BaseModel):
    base_url: str = ""
    project_key: str = ""
    username: str = ""
    api_token: str = ""
    auth_type: str = "basic"
    issue_type: str = "Story"
    test_case_issue_type: str = "Test"


class LLMConfiguration(BaseModel):
    provider: str = "OpenAI"
    model: str = "gpt-4o-mini"
    supervisor_model: str = ""
    api_endpoint: str = ""
    auth_token: str = ""
    temperature: float = 0.2
    browser_timeout_screenshot: float = 30.0
    browser_timeout_navigate: float = 30.0
    browser_use_enabled: bool = False
    browser_use_cdp_url: str = 'http://localhost:9222'
    browser_use_max_steps: int = 25
    browser_use_vision: bool = True
    supervisor_enabled: bool = True
    browser_agent_prompt: str = ''
    browser_provider: str = 'playwright'
    playwright_mcp_enabled: bool = False
    playwright_mcp_command: str = 'npx'
    playwright_mcp_args: list[str] = Field(default_factory=lambda: ['-y', '@playwright/mcp@latest'])


class ApplicationSettings(BaseModel):
    base_url: str = ""
    environment: str = "development"
    default_project: str = ""
    global_parameters: dict[str, str] = Field(default_factory=dict)
    browser_headers: dict[str, str] = Field(default_factory=dict)
    default_follow_links: bool = True


class Configuration(BaseModel):
    jira: JiraConfiguration
    llm: LLMConfiguration
    application: ApplicationSettings


class ConfigurationSaveResponse(BaseModel):
    message: str
    configuration: Configuration


class JiraConnectionResponse(BaseModel):
    connected: bool
    message: str
    details: dict[str, str] = Field(default_factory=dict)


class JiraStorySyncItem(BaseModel):
    story_id: str
    summary: str
    jira_key: str
    jira_url: str | None = None


class JiraStorySyncResponse(BaseModel):
    synced: bool
    message: str
    items: list[JiraStorySyncItem] = Field(default_factory=list)


class LLMConnectionResponse(BaseModel):
    connected: bool
    message: str
    details: dict[str, str] = Field(default_factory=dict)

