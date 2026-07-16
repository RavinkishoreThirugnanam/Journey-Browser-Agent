from pydantic import BaseModel, Field, HttpUrl


class CrawlSettings(BaseModel):
    max_depth: int = 1
    max_pages: int = 8
    follow_links: bool = True


class ExplorationRequest(BaseModel):
    application_url: HttpUrl | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)


class ExplorationResponse(BaseModel):
    message: str
    journey_id: str
    journey_count: int
    exploration_metadata: dict[str, object] = Field(default_factory=dict)
