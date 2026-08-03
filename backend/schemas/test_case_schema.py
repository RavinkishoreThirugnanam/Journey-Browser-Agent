from pydantic import BaseModel, Field


class TestCase(BaseModel):
    test_case_id: str
    generated_at: str = ''
    title: str
    description: str
    preconditions: list[str]
    steps: list[str]
    expected_results: list[str]
    journey_id: str
    user_story_id: str
    user_story: str = ''
    journey_objective: str = ''
    source_evidence: list[dict] = Field(default_factory=list)
    automation_steps: list[dict] = Field(default_factory=list)
    detailed_steps: list[dict] = Field(default_factory=list)
    test_data: dict = Field(default_factory=dict)
    postconditions: list[str] = Field(default_factory=list)
    test_case_type: str = 'Functional'
    scenario_type: str = 'Positive'
    priority: str = 'High'
    environment: str = 'latest'
    component: str = 'Browser Agent'
    epic: str = 'Journey Automation'
    module: str = 'Discovered Journey'
    labels: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    covered_acceptance_criteria: list[dict] = Field(default_factory=list)
    actual_results: str = ''
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
