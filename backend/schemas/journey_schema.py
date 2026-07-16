from pydantic import BaseModel, Field


class Interaction(BaseModel):
    sequence_id: int | str | None = None
    interaction_number: int | None = None
    element_type: str = ''
    element_label: str = ''
    element_id: str | None = None
    selector: str = ''
    selector_type: str = ''
    action: str = ''
    value: str | None = None
    page_url: str = ''
    element_state_before: str | None = None
    element_state_after: str | None = None
    resulted_in: str = ''
    wait_condition: str = ''
    min_length: str | int | None = None
    max_length: str | int | None = None
    expected_text: str | None = None
    validation_message: str | None = None
    api_call_triggered: str | None = None
    api_method: str | None = None
    api_response_status: int | str | None = None
    is_dynamic_element: bool = False
    is_custom_component: bool = False
    is_shadow_dom: bool = False
    iframe_context: str | None = None
    parent_component: str = ''


class JourneyStep(BaseModel):
    step_number: int
    depth_level: int
    page_title: str
    page_url: str
    interactions: list[Interaction] = Field(default_factory=list)


class ExplorationMetadata(BaseModel):
    app_url: str = ''
    starting_feature: str = ''
    task_input: str = ''
    depth_level: int | None = None
    is_pre_login_scoped: bool = False
    total_journeys_discovered: int = 0
    exploration_timestamp: str = ''
    viewport: dict[str, int] = Field(default_factory=dict)
    browser: str = 'chromium'


class JourneyRecord(BaseModel):
    journey_id: str
    journey_title: str = ''
    starting_point: str = ''
    starting_url: str = ''
    outcome: str = ''
    outcome_detail: str = ''
    reasoning: str = ''
    session_boundary_reached: bool = False
    session_boundary_url: str | None = None
    total_depth: int = 0
    test_hints: dict[str, object] = Field(default_factory=dict)
    housekeeping_steps: list[dict[str, object]] = Field(default_factory=list)
    steps: list[JourneyStep] = Field(default_factory=list)
    events: list[Interaction] = Field(default_factory=list)


class ExplorationResult(BaseModel):
    exploration_metadata: ExplorationMetadata
    journeys: list[JourneyRecord] = Field(default_factory=list)


class JourneyDetailResponse(BaseModel):
    journey_id: str
    journey_title: str = ''
    starting_point: str = ''
    starting_url: str = ''
    outcome: str = ''
    outcome_detail: str = ''
    reasoning: str = ''
    session_boundary_reached: bool = False
    session_boundary_url: str | None = None
    total_depth: int = 0
    test_hints: dict[str, object] = Field(default_factory=dict)
    housekeeping_steps: list[dict[str, object]] = Field(default_factory=list)
    steps: list[JourneyStep] = Field(default_factory=list)
    events: list[Interaction] = Field(default_factory=list)
    exploration_metadata: ExplorationMetadata = Field(default_factory=ExplorationMetadata)
    summary: str = ''


class JourneyVisualizeRequest(BaseModel):
    journey_id: str


class JourneyVisualizeResponse(BaseModel):
    journey_id: str
    mermaid: str
