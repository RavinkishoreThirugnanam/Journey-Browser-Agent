from pydantic import BaseModel, Field


class Interaction(BaseModel):
    sequence_id: int | str | None = None
    interaction_number: int | None = None
    element_type: str = ''
    element_label: str = ''
    element_id: str | None = None
    role: str = ''
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
    event_timestamp: str = ''
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    destination_url: str | None = None
    coordinates: dict[str, float] = Field(default_factory=dict)
    network_events: list[dict[str, object]] = Field(default_factory=list)
    dom_snapshot_before: str | None = None
    dom_snapshot_after: str | None = None
    iframe_inventory: list[dict[str, object]] = Field(default_factory=list)
    popup_activity: list[dict[str, object]] = Field(default_factory=list)
    replay: dict[str, object] = Field(default_factory=dict)
    event_id: str = ''
    page_id: str = ''
    route: str = ''
    state_fingerprint_before: str = ''
    state_fingerprint_after: str = ''
    visible_elements: list[dict[str, object]] = Field(default_factory=list)


class JourneyStep(BaseModel):
    step_number: int
    depth_level: int
    page_title: str
    page_url: str
    interactions: list[Interaction] = Field(default_factory=list)


class ExplorationMetadata(BaseModel):
    exploration_id: str = ''
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
    business_assurance: dict[str, object] = Field(default_factory=dict)
    housekeeping_steps: list[dict[str, object]] = Field(default_factory=list)
    steps: list[JourneyStep] = Field(default_factory=list)
    events: list[Interaction] = Field(default_factory=list)


class JourneyBulkDeleteRequest(BaseModel):
    journey_ids: list[str] = Field(min_length=1)


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
    business_assurance: dict[str, object] = Field(default_factory=dict)
    housekeeping_steps: list[dict[str, object]] = Field(default_factory=list)
    steps: list[JourneyStep] = Field(default_factory=list)
    events: list[Interaction] = Field(default_factory=list)
    exploration_metadata: ExplorationMetadata = Field(default_factory=ExplorationMetadata)
    summary: str = ''
    event_count: int = 0


class JourneyVisualizeRequest(BaseModel):
    journey_id: str = ''
    journey_ids: list[str] = Field(default_factory=list)
    root_feature: str = Field(default='', max_length=200)
    mode: str = 'single'


class JourneyVisualizeResponse(BaseModel):
    journey_id: str = ''
    journey_ids: list[str] = Field(default_factory=list)
    root_feature: str = ''
    mode: str = 'single'
    branch_count: int = 0
    mermaid: str
