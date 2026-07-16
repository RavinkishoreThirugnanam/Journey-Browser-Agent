from pydantic import BaseModel, Field


class AcceptanceCriterion(BaseModel):
    ac_type: str
    ac_text: str
    ac_id: str = ''


class Story(BaseModel):
    story_id: str = ''
    journey_id: str = ''
    epic: str
    module: str
    summary: str
    description: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    component: str = 'Browser Agent'


class StoryBundle(BaseModel):
    stories: list[Story] = Field(default_factory=list)


class UserStoryGenerateRequest(BaseModel):
    journey_ids: list[str] = Field(default_factory=list)


class UserStoryListResponse(BaseModel):
    items: list[Story]
    count: int


class StorySyncRequest(BaseModel):
    story_ids: list[str] = Field(default_factory=list)
