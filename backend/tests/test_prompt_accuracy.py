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
    _requires_full_inventory_at_depth,
    _objective_targets,
    _objective_match_score,
    _objective_requests_submenu_inventory,
    _objective_requires_submenu_clicks,
    _objective_submenu_section,
    _objective_submenu_children,
    _validate_objective_input,
    _submenu_destination_candidates,
    _should_hover_target,
    _objective_requires_deterministic_navigation,
    _objective_is_parent_child_scope,
    _objective_parent_is_hover_only,
    _compile_journey_execution_plan,
    _execution_plan_targets,
    _newly_revealed_target_candidates,
    _unique_exact_revealed_target_candidate,
    _collection_resume_tasks,
    _extract_section_child_actions,
    _can_execute_objective_at_depth,
    _authentication_gate_detected,
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


def test_disney_profile_is_scoped_to_requested_resorts_journey():
    objective = (
        "Starting from https://disneyworld.disney.go.com/, navigate only to "
        "Places to Stay -> Disney Resorts Collection. Stop after confirming the destination."
    )
    profile = get_browser_agent_profile("https://disneyworld.disney.go.com/", objective)

    assert "Disney World exploratory navigation agent" in profile
    assert objective in profile
    assert "Do not substitute Tickets, Admission, Parks" in profile
    assert "continue into unrelated branches" in profile
    assert "attempt to discover every Disney journey" in profile


def test_non_disney_profile_remains_generic():
    profile = get_browser_agent_profile(
        "https://example.test/",
        "Explore Preferences and Report Lookup from the sidebar.",
    )

    assert "senior browser journey discovery agent" in profile
    assert "Disney World exploratory navigation agent" not in profile


def test_mermaid_uses_strict_transformer_prompt_and_normalises_output(monkeypatch):
    from services import mermaid_agent_service as mermaid

    captured = {}

    def fake_generate(prompt, payload, **_kwargs):
        captured['prompt'] = prompt
        captured['payload'] = payload
        return 'Here is the diagram:\n```mermaid\nflowchart TD\nA["Start"] --> B["Resorts"]\n```'

    monkeypatch.setattr(mermaid, 'generate_text_with_llm', fake_generate)
    output = mermaid.journey_to_mermaid({'journey_id': 'JRN-001', 'steps': []})

    assert output == 'flowchart TD\nA["Start"] --> B["Resorts"]'
    assert 'strict transformation agent' in captured['prompt']
    assert 'parallel child journey branches' in captured['prompt']
    assert captured['payload']['journey']['journey_id'] == 'JRN-001'


def test_mermaid_fallback_uses_parent_with_parallel_explored_child_branches():
    from services.mermaid_agent_service import _journey_to_mermaid_fallback

    diagram = _journey_to_mermaid_fallback({
        'journey_title': 'Tickets Journey',
        'starting_url': 'https://example.test/',
        'outcome': 'Exploration Complete',
        'steps': [
            {
                'page_url': 'https://example.test/',
                'page_title': 'Home',
                'interactions': [
                    {'action': 'hover', 'element_label': 'Tickets & Parks'},
                    {
                        'action': 'click',
                        'element_label': 'Buy Annual Passes',
                        'destination_url': 'https://example.test/passes/',
                    },
                    {
                        'action': 'click',
                        'element_label': 'Ticket Buying Guide',
                        'destination_url': 'https://example.test/guide/',
                    },
                ],
            },
            {
                'page_url': 'https://example.test/passes/',
                'page_title': 'Annual Passes',
                'interactions': [],
            },
            {
                'page_url': 'https://example.test/guide/',
                'page_title': 'Ticket Buying Guide',
                'interactions': [],
            },
        ],
    })

    assert 'A --> B["Tickets and Parks"]' in diagram
    assert 'B --> N1' in diagram
    assert 'B --> N3' in diagram
    assert 'N1["Buy Annual Passes"]' in diagram
    assert 'N3["Ticket Buying Guide"]' in diagram
    assert diagram.count('["Completed"]') == 2


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


def test_three_step_planning_guide_is_ordered_after_tickets_menu_parent():
    objective = "Explore user journeys for 3-Step Planning Guide under Tickets & Parks"
    assert _objective_targets(objective) == ["tickets parks", "3 step planning guide"]
    parent = ClickCandidate(index=0, text="Tickets & Parks", href="#", tag="a")
    child = ClickCandidate(index=1, text="3-Step Planning Guide", href="/planning/", tag="a", section_heading="Plan Your Visit")
    assert _can_hover_candidate(parent)
    assert _should_hover_target(parent, objective, "tickets parks", "3 step planning guide", [parent])
    assert _objective_match_score(child, objective)[0] > 0


def test_buy_annual_passes_under_tickets_keeps_parent_hover_only_and_child_clickable():
    objective = "Explore user journeys for Buy Annual Passes page under Tickets & Parks"
    assert _objective_targets(objective) == ["tickets and parks", "buy annual passes"]
    assert _objective_is_parent_child_scope(objective)
    assert _objective_parent_is_hover_only(objective, 0)
    assert not _objective_parent_is_hover_only(objective, 1)

    parent = ClickCandidate(index=0, text="Tickets & Parks", href="/admission/", tag="a")
    child = ClickCandidate(index=1, text="Buy Annual Passes", href="/passes/", tag="a")
    assert _should_hover_target(parent, objective, "tickets and parks", "buy annual passes", [parent])
    assert _choose_objective_actions([child], "", objective, target_index=1) == [child]
    assert _objective_requires_submenu_clicks(objective, 0) is False
    assert _objective_requires_submenu_clicks(objective, 1) is True
    plan = _compile_journey_execution_plan(objective)
    assert _execution_plan_targets(plan) == ["tickets and parks", "buy annual passes"]


def test_buy_label_is_safe_when_it_is_navigation_but_not_when_it_submits_purchase():
    from services.browser_agent_service import _is_safe_observation_click

    objective = "Explore user journeys for Buy Annual Passes page under Tickets & Parks"
    assert _is_safe_observation_click("Buy Annual Passes", "a", objective)
    assert not _is_safe_observation_click("Buy Annual Passes", "button", objective)


def test_portal_menu_accepts_only_one_exact_visible_buy_annual_passes_child():
    actions = [
        ClickCandidate(index=0, text="Buy Annual Passes", href="/passes/", tag="a"),
        ClickCandidate(index=1, text="Buy Theme Park Tickets", href="/admission/tickets/", tag="a"),
    ]
    selected = _unique_exact_revealed_target_candidate(
        actions,
        "buy annual passes",
        "https://disneyworld.disney.go.com/",
    )
    assert [candidate.href for candidate in selected] == ["/passes/"]

    duplicated = actions + [ClickCandidate(index=2, text="Buy Annual Passes", href="/other-passes/", tag="a")]
    assert not _unique_exact_revealed_target_candidate(
        duplicated,
        "buy annual passes",
        "https://disneyworld.disney.go.com/",
    )


def test_generic_under_objectives_are_not_disney_specific():
    objective = "Explore account settings under Profile"
    assert _objective_targets(objective) == ["profile", "account settings"]

    inventory_objective = "Explore all links under Products"
    assert _objective_requests_submenu_inventory(inventory_objective)


def test_starting_from_parent_child_objective_is_parsed_in_navigation_order():
    objective = "Explore all possible user journeys starting from Manage MyDisneyExperience Account under Profile Settings"
    assert _objective_targets(objective) == ["profile settings", "manage mydisneyexperience account"]
    assert _objective_is_parent_child_scope(objective)
    assert _requires_full_page_inventory(objective)
    assert not _requires_full_inventory_at_depth(objective, 0)
    assert _requires_full_inventory_at_depth(objective, 1)


def test_generic_profile_and_tickets_objectives_have_clean_parent_child_targets():
    profile = "Explore user journeys for add a guest feature under My family and Friends. My family and Friends are present under MyDisneyExperience"
    tickets = "Explore user journeys for 3-Step Planning Guide under Tickets & Parks"
    assert _objective_targets(profile) == ["mydisneyexperience", "my family and friends", "add a guest feature"]
    assert _objective_targets(tickets) == ["tickets parks", "3 step planning guide"]

    actions = [ClickCandidate(index=0, text="Add a Guest", href="/profile/family-friends/add/", tag="a")]
    assert _choose_objective_actions(actions, "", profile, target_index=2) == actions

    account_menu = ClickCandidate(
        index=1,
        text="My Disney Experience - Press enter to navigate or collapse by pressing escape",
        href="/plan/",
        tag="a",
        role="menuitem",
    )
    assert _choose_objective_actions([account_menu], "", profile, target_index=0) == [account_menu]
    assert _should_hover_target(account_menu, profile, "mydisneyexperience", "my family and friends", [account_menu])

    plan = _compile_journey_execution_plan(profile)
    assert [(step.action, step.target) for step in plan] == [
        ("resolve_parent", "mydisneyexperience"),
        ("resolve_and_continue", "my family and friends"),
        ("resolve_and_explore", "add a guest feature"),
    ]


def test_hovered_portal_child_is_selected_from_newly_revealed_controls():
    before = [ClickCandidate(index=0, text="My Disney Experience", href="/plan/", tag="a", role="menuitem")]
    after = before + [ClickCandidate(index=1, text="My Family & Friends", href="/profile/family-friends/", tag="a")]
    selected = _newly_revealed_target_candidates(
        before,
        after,
        "my family and friends",
        "https://disneyworld.disney.go.com/",
    )
    assert [candidate.text for candidate in selected] == ["My Family & Friends"]


def test_execution_plan_is_generic_for_non_disney_hierarchy():
    objective = "Explore Billing History under Account Settings. Account Settings are present under Profile"
    plan = _compile_journey_execution_plan(objective)
    assert [(step.action, step.target) for step in plan] == [
        ("resolve_parent", "profile"),
        ("resolve_and_continue", "account settings"),
        ("resolve_and_explore", "billing history"),
    ]


def test_collection_plan_and_resume_order_are_explicit():
    objective = "Explore under places to stay disney resorts collection"
    plan = _compile_journey_execution_plan(objective)
    assert [step.action for step in plan] == [
        "resolve_collection_parent",
        "discover_ordered_children",
        "for_each_child_click_and_capture",
        "complete_collection",
    ]


def test_dom_verified_section_children_are_not_rejected_by_imperfect_heading_metadata():
    class FakePage:
        url = "https://disneyworld.disney.go.com/"

        def __init__(self):
            self.calls = 0

        def evaluate(self, _script, *_args):
            self.calls += 1
            if self.calls == 1:
                return [
                    {"text": "View All Disney Accommodations", "href": "/resorts/"},
                    {"text": "Deluxe Villas", "href": "/resorts/deluxe-villas/"},
                    {"text": "Deluxe Resort Hotels", "href": "/resorts/deluxe/"},
                ]
            return [
                {"index": 0, "text": "View All Disney Accommodations", "href": "https://disneyworld.disney.go.com/resorts/", "tag": "a", "section_heading": "Disney Resorts Collection"},
                {"index": 1, "text": "Deluxe Villas", "href": "https://disneyworld.disney.go.com/resorts/deluxe-villas/", "tag": "a", "section_heading": ""},
                {"index": 2, "text": "Deluxe Resort Hotels", "href": "https://disneyworld.disney.go.com/resorts/deluxe/", "tag": "a", "section_heading": "Other Select Deluxe Hotels"},
            ]

    children = _extract_section_child_actions(FakePage(), "Disney Resorts Collection", "Places to Stay")
    assert [child.text for child in children] == [
        "View All Disney Accommodations",
        "Deluxe Villas",
        "Deluxe Resort Hotels",
    ]


def test_collection_keeps_distinct_hash_routed_children_on_same_page():
    actions = [
        ClickCandidate(index=0, text="View All Disney Accommodations", href="https://disneyworld.disney.go.com/resorts/", tag="a"),
        ClickCandidate(index=1, text="Deluxe Villas", href="https://disneyworld.disney.go.com/resorts/#/deluxe-villa", tag="a"),
        ClickCandidate(index=2, text="Deluxe Resort Hotels", href="https://disneyworld.disney.go.com/resorts/#/deluxe", tag="a"),
        ClickCandidate(index=3, text="Moderate Resort Hotels", href="https://disneyworld.disney.go.com/resorts/#/moderate", tag="a"),
        ClickCandidate(index=4, text="Value Resort Hotels", href="https://disneyworld.disney.go.com/resorts/#/value", tag="a"),
        ClickCandidate(index=5, text="Campgrounds", href="https://disneyworld.disney.go.com/resorts/#/campground", tag="a"),
    ]
    children = _submenu_destination_candidates(
        actions,
        "https://disneyworld.disney.go.com/",
        "Places to Stay",
    )
    assert [child.text for child in children] == [action.text for action in actions]


def test_explicit_plan_steps_are_not_limited_by_generic_max_depth_three():
    hierarchy = "Explore Audit Log under Security. Security is present under Administration. Administration is present under Settings"
    collection = "Explore all links under Products"
    assert _can_execute_objective_at_depth(hierarchy, depth=3, max_depth=3)
    assert _can_execute_objective_at_depth(collection, depth=5, max_depth=3)
    assert not _can_execute_objective_at_depth("Explore the homepage", depth=3, max_depth=3)
    assert _collection_resume_tasks(
        "https://example.test/child-1",
        "https://example.test/",
        0,
        2,
        6,
    ) == [
        ("https://example.test/child-1", 1, 6),
        ("https://example.test/", 0, 2),
    ]


def test_parent_only_inventory_objective_has_no_fake_child_target():
    objective = "open the link explore all user journeys under places to stay"
    assert _objective_targets(objective) == ["places to stay"]
    assert _objective_requests_submenu_inventory(objective)


def test_heading_parent_is_inspected_and_child_is_selected_without_clicking_heading():
    objective = "Explore account settings under Profile"
    parent = ClickCandidate(
        index=0,
        text="Profile",
        tag="h2",
        role="heading",
        selector="h2",
        parent_label="Profile",
        parent_tag="h2",
        parent_role="heading",
        parent_interaction="informational_heading",
    )
    child = ClickCandidate(
        index=1,
        text="Account Settings",
        href="/account/settings",
        tag="a",
        selector="a[href='/account/settings']",
        section_heading="Profile",
        parent_label="Profile",
        parent_interaction="container",
    )

    assert _objective_targets(objective) == ["profile", "account settings"]
    assert _choose_objective_actions([parent, child], "", objective, target_index=0) == [parent]
    assert _should_hover_target(parent, objective, "profile", "account settings", [parent])
    assert _choose_objective_actions([parent, child], "", objective, target_index=1) == [child]


def test_under_objectives_bypass_unconstrained_browser_clicking():
    assert _objective_requires_deterministic_navigation(
        "Explore under Places to Stay Disney Resorts Collection"
    )
    assert _objective_requires_deterministic_navigation(
        "Explore 3-Step Planning Guide under Tickets & Parks"
    )
    assert not _objective_requires_deterministic_navigation(
        "Discover the primary user journey from the application home page"
    )


def test_submenu_objective_does_not_scroll_base_page_but_scrolls_destinations():
    objective = "Explore under Places to Stay Disney Resorts Collection"
    assert _requires_full_page_inventory(objective)
    assert not _requires_full_inventory_at_depth(objective, 0)
    assert _requires_full_inventory_at_depth(objective, 1)


def test_scoped_user_journey_scrolls_and_inventories_only_the_child_destination():
    objective = "Explore user journeys for Buy Annual Passes page under Tickets & Parks"

    assert _objective_targets(objective) == ["tickets and parks", "buy annual passes"]
    assert _requires_full_page_inventory(objective)
    assert not _requires_full_inventory_at_depth(objective, 0)
    assert _requires_full_inventory_at_depth(objective, 1)
    plan = _compile_journey_execution_plan(objective)
    assert plan[-1].evidence == "full_page_headings_links_ctas_and_controls"


def test_scoped_destination_inventory_can_be_explicitly_disabled():
    objective = (
        "Explore Billing History under Account Settings. "
        "Stop after confirming the destination and do not scroll."
    )

    assert not _requires_full_page_inventory(objective)


def test_account_destination_login_control_is_classified_as_authentication_gate():
    from schemas.journey_schema import Interaction, JourneyStep

    steps = [JourneyStep(
        step_number=1,
        depth_level=1,
        page_title='Family Friends',
        page_url='https://example.test/profile/family-friends/',
        interactions=[Interaction(
            action='inspect',
            element_label='Log In or Create Account',
            selector='a[href="/login/?appRedirect=/profile/family-friends/"]',
            destination_url='https://example.test/login/?appRedirect=/profile/family-friends/',
        )],
    )]

    assert _authentication_gate_detected(steps, 'https://example.test/')


def test_dynamic_submenu_parent_is_hover_only_before_child_discovery():
    objective = "Explore under Places to Stay Disney Resorts Collection"
    parent = ClickCandidate(index=0, text="Places to Stay", href="/places-to-stay/", tag="a")
    assert _should_hover_target(parent, objective, "places to stay", "", [parent])


def test_disney_places_to_stay_objective_creates_hover_parent_child_path():
    objective = "Explore under Places to Stay Disney Resorts Collection."

    assert _objective_targets(objective) == ["places to stay"]

    parent = ClickCandidate(index=0, text="Places to Stay", href="#", tag="a")
    child = ClickCandidate(index=1, text="View All Disney Accommodations", href="/accommodations/", tag="a")

    assert _should_hover_target(parent, objective, "places to stay", "disney resorts collection", [parent])
    assert not _objective_explicitly_clicks_target(objective, "places to stay", parent)
    assert _objective_requires_submenu_clicks(objective, 1)
    assert _objective_submenu_section(objective) == "disney resorts collection"


def test_repeated_places_to_stay_parent_remains_hover_only():
    objective = (
        "Explore all links under Places to Stay including Disney Resorts Collection: "
        "View All Disney Accommodations, Deluxe Villas, Deluxe Resort Hotels, "
        "Moderate Resort Hotels, Value Resort Hotels, Campgrounds."
    )
    assert _objective_requires_submenu_clicks(objective, 2) is False


def test_submenu_inventory_queues_all_visible_same_origin_children():
    objective = "Explore all links under Places to Stay, including Disney Resorts Collection."
    assert _objective_requests_submenu_inventory(objective)

    actions = [
        ClickCandidate(index=0, text="Disney Resorts Collection", href="https://disneyworld.disney.go.com/resorts/", tag="a"),
        ClickCandidate(index=1, text="View All Disney Accommodations", href="https://disneyworld.disney.go.com/accommodations/", tag="a"),
        ClickCandidate(index=2, text="External", href="https://example.test/", tag="a"),
    ]
    children = _submenu_destination_candidates(actions, "https://disneyworld.disney.go.com/", "Places to Stay")

    assert [child.text for child in children] == [
        "Disney Resorts Collection",
        "View All Disney Accommodations",
    ]
    assert _objective_requires_submenu_clicks(objective, 0) is False
    assert _objective_requires_submenu_clicks(objective, 1) is True


def test_section_heading_is_not_treated_as_a_child_destination():
    actions = [
        ClickCandidate(index=0, text="Disney Resorts Collection", href="/resorts/", tag="a", section_heading="Tickets & Parks"),
        ClickCandidate(index=1, text="View All Disney Accommodations", href="/accommodations/", tag="a", section_heading="Disney Resorts Collection"),
    ]
    children = _submenu_destination_candidates(
        actions,
        "https://disneyworld.disney.go.com/",
        "Places to Stay",
        "Disney Resorts Collection",
    )
    assert [candidate.text for candidate in children] == ["View All Disney Accommodations"]


def test_submenu_children_can_match_section_through_nearest_parent_relationship():
    actions = [
        ClickCandidate(
            index=0,
            text="View All Disney Accommodations",
            href="https://disneyworld.disney.go.com/accommodations/",
            tag="a",
            parent_label="Disney Resorts Collection",
            parent_selector="nav section",
        ),
        ClickCandidate(
            index=1,
            text="Deluxe Villas",
            href="https://disneyworld.disney.go.com/villas/",
            tag="a",
            parent_label="Disney Resorts Collection",
            parent_selector="nav section",
        ),
        ClickCandidate(
            index=2,
            text="View Special Offers",
            href="https://disneyworld.disney.go.com/offers/",
            tag="a",
            parent_label="Featured Items",
        ),
    ]
    children = _submenu_destination_candidates(
        actions,
        "https://disneyworld.disney.go.com/",
        "Places to Stay",
        "Disney Resorts Collection",
    )
    assert [candidate.text for candidate in children] == ["View All Disney Accommodations", "Deluxe Villas"]


def test_disney_resorts_section_filters_heading_children_without_clicking_heading():
    objective = "Hover Places to Stay and explore all links under Disney Resorts Collection."
    assert _objective_submenu_section(objective) == "disney resorts collection"

    actions = [
        ClickCandidate(index=0, text="View All Disney Accommodations", href="https://disneyworld.disney.go.com/accommodations/", tag="a", section_heading="Disney Resorts Collection"),
        ClickCandidate(index=1, text="Deluxe Villas", href="https://disneyworld.disney.go.com/villas/", tag="a", section_heading="Disney Resorts Collection"),
        ClickCandidate(index=2, text="View Special Offers", href="https://disneyworld.disney.go.com/offers/", tag="a", section_heading="Featured Items"),
    ]
    from services.browser_agent_service import _submenu_destination_candidates
    children = _submenu_destination_candidates(actions, "https://disneyworld.disney.go.com/", "Places to Stay", "Disney Resorts Collection")

    assert [child.text for child in children] == ["View All Disney Accommodations", "Deluxe Villas"]


def test_disney_objective_parses_parent_and_all_numbered_children():
    objective = (
        "Starting from https://disneyworld.disney.go.com/, hover over the Places to Stay navigation item "
        "and wait for the submenu. Under the Disney Resorts Collection section, explore each visible link "
        "one by one: 1. View All Disney Accommodations 2. Deluxe Villas 3. Deluxe Resort Hotels "
        "4. Moderate Resort Hotels 5. Value Resort Hotels 6. Campgrounds. For each link, click it."
    )
    assert _objective_submenu_children(objective) == [
        "view all disney accommodations",
        "deluxe villas",
        "deluxe resort hotels",
        "moderate resort hotels",
        "value resort hotels",
        "campgrounds",
    ]
    assert _objective_targets(objective) == [
        "places to stay", "view all disney accommodations", "places to stay",
        "deluxe villas", "places to stay", "deluxe resort hotels", "places to stay",
        "moderate resort hotels", "places to stay", "value resort hotels",
        "places to stay", "campgrounds",
    ]


def test_contaminated_objectives_are_rejected():
    try:
        _validate_objective_input('Starting from https://one.test. Starting from https://two.test.')
    except ValueError as exc:
        assert 'multiple objectives' in str(exc)
    else:
        raise AssertionError('Expected contaminated objective to be rejected')


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


def test_generic_homepage_inventory_is_complete_only_on_landing_page():
    objective = "Discover the primary user journey from the application home page."
    assert _requires_full_inventory_at_depth(objective, 0)
    assert not _requires_full_inventory_at_depth(objective, 1)
    assert _requires_full_inventory_at_depth("Explore all pages and capture all links.", 2)

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


def test_page_name_prefers_primary_content_heading_over_navigation_heading_and_document_title():
    from services.browser_agent_service import _derive_page_name

    assert _derive_page_name(
        "https://example.test/family-vacation-guide/",
        "Family Vacation Planning Guide | Example",
        ["Family Vacation Planning Guide"],
        "Family Vacation Planning Guide",
    ) == "Family Vacation Planning Guide"


def test_page_name_uses_document_title_before_unscoped_heading_fallback():
    from services.browser_agent_service import _derive_page_name

    assert _derive_page_name(
        "https://example.test/family-vacation-guide/",
        "Family Vacation Planning Guide | Example",
        ["Tickets and Passes"],
    ) == "Family Vacation Planning Guide | Example"


def test_mermaid_payload_excludes_raw_dom_and_screenshot_navigation_noise():
    from services.mermaid_agent_service import _mermaid_payload

    payload = _mermaid_payload({
        "journey_title": "Family Vacation Guide",
        "steps": [{
            "step_number": 1,
            "page_title": "Family Vacation Guide",
            "page_url": "https://example.test/family-vacation-guide/",
            "interactions": [{
                "action": "open",
                "element_label": "Family Vacation Guide",
                "resulted_in": "page_load",
                "dom_snapshot_after": "<nav><h2>Tickets and Passes</h2></nav>",
                "screenshot_after": "tickets-and-passes.png",
            }],
        }],
    })

    serialized = str(payload)
    assert "Family Vacation Guide" in serialized
    assert "Tickets and Passes" not in serialized
    assert "screenshot_after" not in serialized


def test_mermaid_payload_repairs_stored_navigation_title_from_snapshot_document_title():
    from services.mermaid_agent_service import _mermaid_payload

    payload = _mermaid_payload({
        "steps": [{
            "page_title": "Tickets and Passes",
            "page_url": "https://example.test/family-vacation-guide/",
            "interactions": [{
                "action": "open",
                "dom_snapshot_after": "<html><head><title>Family Vacation Planning Guide</title></head><body></body></html>",
            }],
        }],
    })

    assert payload["steps"][0]["page_title"] == "Family Vacation Planning Guide"
