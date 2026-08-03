from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from services.live_browser_service import navigate_live_browser, replay_live_browser

router = APIRouter()


class LiveBrowserNavigateRequest(BaseModel):
    url: HttpUrl


class LiveBrowserReplayRequest(BaseModel):
    url: HttpUrl
    events: list[dict] = Field(default_factory=list)

@router.post('/browser/live/navigate')
def navigate(request: LiveBrowserNavigateRequest):
    try:
        return navigate_live_browser(str(request.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Live browser connection failed: {type(exc).__name__}: {exc}') from exc

@router.post('/browser/live/replay')
def replay(request: LiveBrowserReplayRequest):
    try:
        return replay_live_browser(str(request.url), request.events)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f'Live browser replay unavailable: {type(exc).__name__}: {exc}') from exc