from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    ac_type: str
    ac_text: str
    ac_id: str = ''


class Story(BaseModel):
    story_id: str = ''
    journey_id: str = ''
    generated_at: str = ''
    generation_source: str = ''
    generation_model: str = ''
    epic: str
    module: str
    summary: str
    description: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    component: str = 'Browser Agent'
    jira_key: str = ''
    jira_url: str = ''
    jira_sync_status: str = 'local'
    jira_updated_at: str = ''
    jira_last_refreshed_at: str = ''
    jira_sync_error: str = ''


class StoryBundle(BaseModel):
    stories: list[Story] = Field(default_factory=list)
    generation_source: str = ''
    generation_model: str = ''
    generation_warning: str = ''


class UserStoryGenerateRequest(BaseModel):
    journey_ids: list[str] = Field(default_factory=list)


class UserStoryListResponse(BaseModel):
    items: list[Story]
    count: int


class StorySyncRequest(BaseModel):
    story_ids: list[str] = Field(default_factory=list)