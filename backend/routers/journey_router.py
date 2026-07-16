from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas.journey_schema import JourneyDetailResponse, JourneyVisualizeRequest, JourneyVisualizeResponse
from services.artifact_file_service import write_text_file, unique_filename
from services.journey_map_service import clear_journeys, delete_journey, get_journey, list_journeys
from services.mermaid_agent_service import journey_to_mermaid

router = APIRouter()


def _journey_to_detail(journey: dict) -> dict:
    return {
        **journey,
        'summary': f"{len(journey.get('steps', []))} steps captured from {journey.get('starting_url', journey.get('source_url', journey.get('application_url', '')))}.",
    }


@router.get('/journeys')
def journeys():
    return list_journeys()


@router.delete('/journeys')
def reset_journeys():
    clear_journeys()
    return {'message': 'Journey data cleared'}


@router.delete('/journeys/{journey_id}')
def remove_journey(journey_id: str):
    deleted = delete_journey(journey_id)
    if not deleted:
        raise HTTPException(status_code=404, detail='Journey not found')
    return {'message': 'Journey deleted', 'journey_id': journey_id}


@router.get('/journeys/{journey_id}', response_model=JourneyDetailResponse)
def journey_detail(journey_id: str):
    journey = get_journey(journey_id)
    if not journey:
        raise HTTPException(status_code=404, detail='Journey not found')
    return _journey_to_detail(journey)


@router.post('/journeys/visualize', response_model=JourneyVisualizeResponse)
def visualize(payload: JourneyVisualizeRequest):
    journey = get_journey(payload.journey_id)
    if not journey:
        raise HTTPException(status_code=404, detail='Journey not found')
    return JourneyVisualizeResponse(journey_id=payload.journey_id, mermaid=journey_to_mermaid(journey))


@router.get('/journeys/{journey_id}/mermaid/download')
def download_mermaid(journey_id: str):
    journey = get_journey(journey_id)
    if not journey:
        raise HTTPException(status_code=404, detail='Journey not found')
    mermaid = journey_to_mermaid(journey)
    filename = unique_filename(f'journey_{journey_id}_mermaid', '.mmd')
    path = write_text_file(filename, mermaid)
    return FileResponse(path, filename=filename, media_type='text/plain')
