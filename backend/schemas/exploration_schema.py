from pydantic import BaseModel, Field, HttpUrl


class CrawlSettings(BaseModel):
    max_depth: int = 3
    max_pages: int = 8
    follow_links: bool = True
    min_events: int = 10


class ExplorationRequest(BaseModel):
    application_url: HttpUrl | None = None
    objective: str = Field(default='Discover the primary user journey from the application home page.', min_length=5, max_length=6000)
    stream_key: str = Field(default='', max_length=128, pattern=r'^[A-Za-z0-9_.-]*$')
    parameters: dict[str, str] = Field(default_factory=dict)
    crawl: CrawlSettings = Field(default_factory=CrawlSettings)


class ExplorationResponse(BaseModel):
    message: str
    journey_id: str
    journey_count: int
    outcome: str = ''
    outcome_detail: str = ''
    exploration_metadata: dict[str, object] = Field(default_factory=dict)


