from pydantic import BaseModel, Field


class TestScript(BaseModel):
    script_id: str
    test_case_id: str
    generated_at: str = ''
    feature_file: str
    javascript_file: str
    feature_filename: str = ''
    javascript_filename: str = ''
    journey_id: str = ''
    user_story_id: str = ''
    journey_objective: str = ''
    source_evidence_count: int = 0


class TestScriptGenerateRequest(BaseModel):
    test_case_ids: list[str] = Field(default_factory=list)


class TestScriptListResponse(BaseModel):
    items: list[TestScript]
    count: int