from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.journey_schema import JourneyBulkDeleteRequest, JourneyDetailResponse, JourneyVisualizeRequest, JourneyVisualizeResponse
from services.artifact_file_service import write_text_file, unique_filename
from services.journey_map_service import cleanup_orphan_artifacts, clear_journeys, delete_journey, delete_journeys, get_journey, list_journeys, list_journey_summaries
from services.mermaid_agent_service import journey_to_mermaid, journeys_to_mermaid

router = APIRouter()


def _compact_page_evidence(journey: dict) -> None:
    """Keep one representative DOM, screenshot and inventory per explored URL."""
    representatives: dict[str, dict] = {}
    removable_fields = {
        'dom_snapshot_before', 'dom_snapshot_after', 'screenshot_before', 'screenshot_after',
        'network_events', 'iframe_inventory', 'popup_activity', 'visible_elements',
    }
    for step_index, step in enumerate(journey.get('steps', []) or []):
        if not isinstance(step, dict):
            continue
        page_key = str(step.get('page_url') or f'step-{step_index}')
        for interaction in step.get('interactions', []) or []:
            if not isinstance(interaction, dict):
                continue
            representative = representatives.setdefault(page_key, {'interaction': interaction})
            representative['interaction'] = interaction
            dom_snapshot = interaction.get('dom_snapshot_after') or interaction.get('dom_snapshot_before')
            screenshot = interaction.get('screenshot_after') or interaction.get('screenshot_before')
            visible_elements = interaction.get('visible_elements')
            if dom_snapshot:
                representative['dom_snapshot_after'] = dom_snapshot
            if screenshot:
                representative['screenshot_after'] = screenshot
            if visible_elements:
                representative['visible_elements'] = visible_elements
            for field in removable_fields:
                interaction.pop(field, None)

    for representative in representatives.values():
        interaction = representative.pop('interaction')
        interaction.update(representative)


def _journey_to_detail(journey: dict, include_evidence: bool = True) -> dict:
    event_count = len(journey.get('events', []) or []) or sum(
        len(step.get('interactions', []) or [])
        for step in journey.get('steps', []) or []
        if isinstance(step, dict)
    )
    if include_evidence:
        _compact_page_evidence(journey)
    else:
        heavy_fields = {
            'dom_snapshot_before', 'dom_snapshot_after', 'screenshot_before', 'screenshot_after',
            'network_events', 'iframe_inventory', 'popup_activity', 'visible_elements',
        }
        for step in journey.get('steps', []) or []:
            for interaction in step.get('interactions', []) or []:
                if isinstance(interaction, dict):
                    for field in heavy_fields:
                        interaction.pop(field, None)
        journey['events'] = []
        test_hints = journey.get('test_hints')
        if isinstance(test_hints, dict):
            for field in {'candidate_ledger', 'page_ids', 'event_ids'}:
                test_hints.pop(field, None)
    return {
        **journey,
        'event_count': event_count,
        'summary': f"{len(journey.get('steps', []))} steps captured from {journey.get('starting_url', journey.get('source_url', journey.get('application_url', '')))}.",
    }


@router.get('/journeys')
def journeys(compact: bool = False):
    return list_journey_summaries() if compact else list_journeys()


@router.delete('/journeys')
def reset_journeys():
    cleanup = clear_journeys()
    return {'message': 'Journey data cleared', **cleanup}


@router.post('/journeys/delete-selected')
def remove_selected_journeys(payload: JourneyBulkDeleteRequest):
    result = delete_journeys(set(payload.journey_ids))
    return {'message': f"{result['deleted_count']} journey discoveries deleted", **result}

@router.delete('/journeys/{journey_id}')
def remove_journey(journey_id: str):
    result = delete_journey(journey_id)
    if not result.get('deleted'):
        raise HTTPException(status_code=404, detail='Journey not found')
    return {'message': 'Journey deleted', 'journey_id': journey_id, **result}



@router.delete('/journeys/artifacts/orphans')
def remove_orphan_artifacts():
    cleanup = cleanup_orphan_artifacts()
    return {'message': 'Orphan local artifacts cleaned', **cleanup}
@router.get(
    '/journeys/{journey_id}',
    response_model=JourneyDetailResponse,
    response_model_exclude_none=True,
    response_model_exclude_defaults=True,
)
def journey_detail(journey_id: str, include_evidence: bool = True):
    journey = get_journey(journey_id)
    if not journey:
        raise HTTPException(status_code=404, detail='Journey not found')
    return _journey_to_detail(journey, include_evidence=include_evidence)


@router.post('/journeys/visualize', response_model=JourneyVisualizeResponse)
def visualize(payload: JourneyVisualizeRequest):
    requested_ids = payload.journey_ids if payload.mode == 'consolidated' or payload.journey_ids else [payload.journey_id]
    journey_ids = list(dict.fromkeys(journey_id.strip() for journey_id in requested_ids if journey_id.strip()))
    if not journey_ids:
        raise HTTPException(status_code=422, detail='Select at least one journey to visualize')
    if len(journey_ids) > 25:
        raise HTTPException(status_code=422, detail='A consolidated map supports up to 25 journeys')

    journeys = []
    for journey_id in journey_ids:
        journey = get_journey(journey_id)
        if not journey:
            raise HTTPException(status_code=404, detail=f'Journey not found: {journey_id}')
        journeys.append(journey)

    consolidated = payload.mode == 'consolidated' or bool(payload.journey_ids)
    if consolidated:
        root_feature = payload.root_feature.strip() or 'Consolidated Journey Map'
        mermaid = journeys_to_mermaid(journeys, root_feature)
        return JourneyVisualizeResponse(
            journey_id=journey_ids[0],
            journey_ids=journey_ids,
            root_feature=root_feature,
            mode='consolidated',
            branch_count=len(journeys),
            mermaid=mermaid,
        )

    return JourneyVisualizeResponse(
        journey_id=journey_ids[0],
        journey_ids=journey_ids,
        branch_count=1,
        mermaid=journey_to_mermaid(journeys[0]),
    )


@router.get('/journeys/{journey_id}/mermaid/download')
def download_mermaid(journey_id: str):
    journey = get_journey(journey_id)
    if not journey:
        raise HTTPException(status_code=404, detail='Journey not found')
    mermaid = journey_to_mermaid(journey)
    filename = unique_filename(f'journey_{journey_id}_mermaid', '.mmd')
    path = write_text_file(filename, mermaid)
    return FileResponse(path, filename=filename, media_type='text/plain')
