from pydantic import BaseModel, Field


class TestScript(BaseModel):
    script_id: str
    test_case_id: str
    feature_file: str
    javascript_file: str


class TestScriptGenerateRequest(BaseModel):
    test_case_ids: list[str] = Field(default_factory=list)


class TestScriptListResponse(BaseModel):
    items: list[TestScript]
    count: int
