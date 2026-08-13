from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.logging import configure_logging
from routers.configuration_router import router as configuration_router
from routers.dashboard_router import router as dashboard_router
from routers.exploration_router import router as exploration_router
from routers.export_router import router as export_router
from routers.journey_router import router as journey_router
from routers.live_browser_router import router as live_browser_router
from routers.live_event_router import router as live_event_router
from routers.pipeline_router import router as pipeline_router
from routers.reporting_router import router as reporting_router
from routers.summary_router import router as summary_router
from routers.test_case_router import router as test_case_router
from routers.test_script_router import router as test_script_router
from routers.user_story_router import router as user_story_router


configure_logging()

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(exploration_router, prefix="/api/v1", tags=["exploration"])
app.include_router(journey_router, prefix="/api/v1", tags=["journeys"])
app.include_router(live_browser_router, prefix="/api/v1", tags=["live-browser"])
app.include_router(live_event_router, prefix="/api/v1", tags=["live-browser-events"])
app.include_router(configuration_router, prefix="/api/v1", tags=["configuration"])
app.include_router(dashboard_router, prefix="/api/v1", tags=["dashboard"])
app.include_router(user_story_router, prefix="/api/v1", tags=["user-stories"])
app.include_router(test_case_router, prefix="/api/v1", tags=["test-cases"])
app.include_router(test_script_router, prefix="/api/v1", tags=["test-scripts"])
app.include_router(export_router, prefix="/api/v1", tags=["export"])
app.include_router(pipeline_router, prefix="/api/v1", tags=["pipeline"])
app.include_router(reporting_router, prefix="/api/v1", tags=["reporting"])
app.include_router(summary_router, prefix="/api/v1", tags=["summary"])


@app.get("/health")
def health():
    return {"status": "ok", "app_name": settings.app_name}
