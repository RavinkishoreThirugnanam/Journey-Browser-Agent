from fastapi import APIRouter, HTTPException

from schemas.exploration_schema import ExplorationRequest, ExplorationResponse
from services.browser_agent_service import explore_application
from services.journey_map_service import save_journey
from routers.configuration_router import _read as read_configuration

router = APIRouter()


@router.post('/exploration/start', response_model=ExplorationResponse)
def start_exploration(payload: ExplorationRequest):
    try:
        application_url = str(payload.application_url) if payload.application_url else ''
        if not application_url or application_url == 'None':
            application_url = read_configuration().get('application', {}).get('base_url', '')
        exploration = explore_application(application_url, payload.parameters, payload.crawl.model_dump())
        save_journey(exploration)
        first_journey_id = exploration.journeys[0].journey_id if exploration.journeys else ''
        return ExplorationResponse(message='Exploration started successfully', journey_id=first_journey_id, journey_count=len(exploration.journeys))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Exploration failed: {exc}') from exc
