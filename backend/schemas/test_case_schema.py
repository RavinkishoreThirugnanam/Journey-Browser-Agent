from pydantic import BaseModel, Field


class TestCase(BaseModel):
    test_case_id: str
    title: str
    description: str
    preconditions: list[str]
    steps: list[str]
    expected_results: list[str]
    journey_id: str
    user_story_id: str
    jira_key: str = ''
    jira_url: str = ''
    jira_issue_type: str = ''
    sync_status: str = 'local'
    sync_error: str = ''


class TestCaseGenerateRequest(BaseModel):
    journey_ids: list[str] = Field(default_factory=list)
    user_story_ids: list[str] = Field(default_factory=list)


class TestCaseListResponse(BaseModel):
    items: list[TestCase]
    count: int


class TestCaseGenerateResponse(BaseModel):
    items: list[TestCase]
    count: int
    jira_synced_count: int = 0
    jira_failed_count: int = 0
