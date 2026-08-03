from services.agent_prompts import get_browser_agent_profile
from services.browser_agent_service import (
    ClickCandidate,
    _build_llm_browser_task,
    _capture_full_page_inventory,
    _generic_internal_link_candidates,
    _can_hover_candidate,
    _choose_objective_actions,
    _is_consent_objective_target,
    _is_safe_observation_click,
    _objective_explicitly_clicks_target,
    _objective_requires_hover,
    _requires_full_page_inventory,
    _objective_targets,
    _should_hover_target,
)
from services.jira_agent_service import _normalise_story
from services.test_case_agent_service import _normalise_case
from services.test_script_agent_service import _normalise_script


def test_disney_profile_keeps_journey_objective_authoritative():
    objective = "Hover over Tickets & Parks and click View Special Offers. Confirm /special-offers/."
    profile = get_browser_agent_profile("https://disneyworld.disney.go.com/", objective)

    assert objective in profile
    assert "Use this exact exploration plan" not in profile
    assert "Explore Buy theme Park Tickets" not in profile
    assert "Never substitute a familiar site flow" in profile


def test_objective_target_wins_over_familiar_domain_action():
    objective = "Hover over Tickets & Parks and click View Special Offers. Confirm /special-offers/."
    profile = get_browser_agent_profile("https://disneyworld.disney.go.com/", objective)
    actions = [
        ClickCandidate(index=0, text="Theme Park Tickets", href="/admission/", tag="a"),
        ClickCandidate(index=1, text="View Special Offers", href="/special-offers/", tag="a"),
    ]

    selected = _choose_objective_actions(actions, profile, objective, target_index=1)

    assert selected
    assert selected[0].text == "View Special Offers"


def test_browser_task_contains_objective_completion_contract():
    objective = "Explore Preferences and Report Lookup from the sidebar."
    task = _build_llm_browser_task("https://example.test/", objective, 4, 8, 10)

    assert objective in task
    assert "journey objective is the source of truth" in task
    assert "Never report success for a different destination" in task
    assert "matched_targets" in task
    assert "missing_targets" in task


def test_generated_artifacts_cannot_replace_source_traceability():
    objective = "Explore Preferences"
    journey = {
        "journey_id": "JRN-source",
        "starting_url": "https://example.test/",
        "test_hints": {"journey_objective": objective},
        "steps": [],
    }
    story = {
        "story_id": "US-source",
        "journey_id": "JRN-source",
        "summary": "US-01 Explore Preferences",
        "description": "Source story",
        "acceptance_criteria": [],
    }

    normalised_story = _normalise_story(
        {
            "journey_id": "JRN-invented",
            "epic": "Settings",
            "module": "Preferences",
            "summary": "US-01 Explore Preferences",
            "description": "As a user, I want Preferences at https://example.test/.",
            "acceptance_criteria": [],
        },
        journey,
        1,
    )
    assert normalised_story.journey_id == "JRN-source"

    normalised_case = _normalise_case(
        {
            "journey_id": "JRN-invented",
            "user_story_id": "US-invented",
            "journey_objective": "Purchase tickets",
            "title": "Validate Preferences",
        },
        story,
        journey,
    )
    assert normalised_case.journey_id == "JRN-source"
    assert normalised_case.user_story_id == "US-source"
    assert normalised_case.journey_objective == objective

    normalised_script = _normalise_script(
        {
            "test_case_id": "TC-invented",
            "journey_id": "JRN-invented",
            "user_story_id": "US-invented",
            "journey_objective": "Purchase tickets",
        },
        {
            **normalised_case.model_dump(),
            "test_case_id": "TC-source",
        },
    )
    assert normalised_script.test_case_id == "TC-source"
    assert normalised_script.journey_id == "JRN-source"
    assert normalised_script.user_story_id == "US-source"
    assert normalised_script.journey_objective == objective


def test_cookie_consent_is_clicked_only_when_objective_authorizes_it():
    accept = ClickCandidate(index=0, text="Accept All", tag="button", role="button")
    objective = "Click Accept All, then explore Data and AI, Functional Expertise, Industries, Knowledge Hub, Company, and Contact."

    assert _objective_targets(objective) == [
        "accept all",
        "data and ai",
        "functional expertise",
        "industries",
        "knowledge hub",
        "company",
        "contact",
    ]
    assert _is_safe_observation_click(accept.text, accept.tag, objective)
    assert not _is_safe_observation_click(accept.text, accept.tag, "Explore the homepage")
    assert not _can_hover_candidate(accept)
    selected = _choose_objective_actions([accept], "", objective, target_index=0)
    assert selected == [accept]

def test_factspan_cloud_data_engineering_hover_journey_keeps_parent_and_child():
    objective = (
        "Starting from Factspan, navigate specifically to Cloud Data Engineering. "
        "If a cookie-consent banner appears, click Accept All. "
        "Hover over Data and AI, wait for the mega menu, then click Cloud Data Engineering. "
        "Verify the URL contains /cloud-data-engineering/."
    )
    parent = ClickCandidate(index=0, text="Data and AI", href="/data-science-ai/", tag="a")
    child = ClickCandidate(index=1, text="Cloud Data Engineering", href="/cloud-data-engineering/", tag="a")

    assert _objective_targets(objective) == [
        "accept all",
        "data and ai",
        "cloud data engineering",
    ]
    assert _is_consent_objective_target("Accept All")
    assert _can_hover_candidate(parent)
    assert _choose_objective_actions([parent, child], "", objective, target_index=1) == [parent]
    assert _choose_objective_actions([parent, child], "", objective, target_index=2) == [child]

def test_explicit_hover_never_falls_through_to_parent_click():
    objective = "Hover over Data and AI without clicking the parent, then click Cloud Data Engineering."
    parent = ClickCandidate(index=0, text="Data and AI", href="/data-science-ai/", tag="a")
    child = ClickCandidate(index=1, text="Cloud Data Engineering", href="/cloud-data-engineering/", tag="a")

    assert _objective_requires_hover(objective, "data and ai", parent)
    assert not _objective_explicitly_clicks_target(objective, "data and ai", parent)
    assert _objective_explicitly_clicks_target(objective, "cloud data engineering", child)
    assert _should_hover_target(parent, objective, "data and ai", "cloud data engineering", [parent])


def test_visible_sibling_does_not_turn_click_sequence_into_hover_sequence():
    objective = "Click Report Lookup, then click Preferences."
    report = ClickCandidate(index=0, text="Report Lookup", href="/reports", tag="a")
    preferences = ClickCandidate(index=1, text="Preferences", href="/preferences", tag="a")

    assert _can_hover_candidate(report)
    assert not _objective_requires_hover(objective, "report lookup", report)
    assert not _should_hover_target(report, objective, "report lookup", "preferences", [report, preferences])


def test_explicit_hover_overrides_menu_name_heuristic():
    objective = "Hover over Solutions and inspect the opened menu."
    solutions = ClickCandidate(index=0, text="Solutions", href="/solutions", tag="a")

    assert not _can_hover_candidate(solutions)
    assert _should_hover_target(solutions, objective, "solutions", "", [solutions])

def test_unknown_menu_names_are_extracted_from_explicit_hover_flow():
    objective = (
        "Hover over Solutions in the main navigation, wait until the menu is visible, "
        "then click Platform Overview."
    )
    parent = ClickCandidate(index=0, text="Solutions", href="/solutions", tag="a")

    assert _objective_targets(objective) == ["solutions", "platform overview"]
    assert _objective_requires_hover(objective, "solutions", parent)
    assert _should_hover_target(parent, objective, "solutions", "platform overview", [parent])

def test_generic_homepage_discovery_enables_full_page_inventory():
    assert _requires_full_page_inventory("Discover the primary user journey from the application home page.")
    assert _requires_full_page_inventory("Explore the homepage and scroll from top to bottom.")
    assert not _requires_full_page_inventory("Hover over Products and click Platform Overview.")


def test_generic_internal_links_are_safe_same_origin_and_deduplicated():
    actions = [
        ClickCandidate(index=0, text="About", href="/about#team", tag="a"),
        ClickCandidate(index=1, text="About duplicate", href="https://example.test/about", tag="a"),
        ClickCandidate(index=2, text="Buy now", href="/checkout", tag="a"),
        ClickCandidate(index=3, text="External", href="https://external.test/page", tag="a"),
        ClickCandidate(index=4, text="Services", href="/services", tag="a"),
    ]

    selected = _generic_internal_link_candidates(
        actions,
        "https://example.test/",
        "https://example.test/",
        "Explore the complete homepage.",
    )

    assert [candidate.text for candidate in selected] == ["About", "Services"]


def test_full_page_inventory_scrolls_to_bottom_and_keeps_all_new_controls(monkeypatch):
    from services import browser_agent_service as service

    class FakePage:
        def __init__(self):
            self.y = 0
            self.viewport = 800
            self.height = 2400

        def evaluate(self, script, arg=None):
            if arg is not None:
                self.y = min(int(arg), self.height - self.viewport)
                return None
            if "scrollTo(0, 0)" in script:
                self.y = 0
                return None
            if "return {" in script:
                return {"y": self.y, "viewport": self.viewport, "height": self.height}
            if "Math.max" in script:
                return self.height
            return None

        def wait_for_timeout(self, _milliseconds):
            return None

    page = FakePage()
    monkeypatch.setattr(
        service,
        "_extract_clickable_actions",
        lambda current_page: [
            ClickCandidate(
                index=current_page.y,
                text=f"Control at {current_page.y}",
                href=f"/page-{current_page.y}",
                tag="a",
                selector=f"#control-{current_page.y}",
            )
        ],
    )
    monkeypatch.setattr(service, "_capture_viewport_screenshot", lambda *_args, **_kwargs: "screenshot.png")
    monkeypatch.setattr(service, "_capture_dom_snapshot", lambda *_args, **_kwargs: "<main><h1>Complete</h1></main>")
    monkeypatch.setattr(service, "_publish_agent_event", lambda *_args, **_kwargs: None)

    interactions, next_sequence, controls, summary = _capture_full_page_inventory(
        page,
        1,
        "https://example.test/",
        "https://example.test/",
    )

    assert page.y == 1600
    assert summary["scroll_count"] >= 2
    assert summary["control_count"] == len(controls) >= 3
    assert any(interaction.action == "scroll" for interaction in interactions)
    assert interactions[-1].element_label == "Full page inventory"
    assert next_sequence > len(interactions)


def test_live_preview_scroll_is_paced_and_pointer_is_rendered():
    from services.live_browser_service import scroll_live_page

    class FakeMouse:
        def __init__(self):
            self.moves = []

        def move(self, x, y, steps=1):
            self.moves.append((x, y, steps))

    class FakePage:
        def __init__(self):
            self.y = 0
            self.positions = []
            self.pointer_payloads = []
            self.mouse = FakeMouse()
            self.foreground_count = 0

        def bring_to_front(self):
            self.foreground_count += 1

        def evaluate(self, script, arg=None):
            if isinstance(arg, dict):
                self.pointer_payloads.append(arg)
                return None
            if arg is not None:
                self.y = int(arg)
                self.positions.append(self.y)
                return None
            if 'scrollTop' in script:
                return self.y
            return None

        def wait_for_timeout(self, _milliseconds):
            return None

    page = FakePage()
    scroll_live_page(page, 720, 'Scrolling inventory')

    assert page.foreground_count >= 1
    assert len(page.positions) >= 4
    assert page.positions[-1] == 720
    assert page.pointer_payloads[-1]['label'] == 'Scrolling inventory'
    assert page.mouse.moves