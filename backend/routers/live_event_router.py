from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from services.live_event_service import iter_sse

router = APIRouter()


@router.get('/browser/live/events')
def live_events(url: str = Query(..., min_length=8)):
    return StreamingResponse(
        iter_sse(url),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'},
    )