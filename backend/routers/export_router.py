from fastapi import APIRouter
from fastapi.responses import FileResponse

from services.artifact_file_service import GENERATED_DIR
from services.export_service import create_export_file, export_artifact

router = APIRouter()


def _journey_ids(value: str | None) -> list[str]:
    return [item for item in (value or "").split(",") if item]


@router.get("/export/{artifact_type}")
def export(artifact_type: str, preview: bool = False, journey_ids: str | None = None):
    return export_artifact(artifact_type, preview=preview, journey_ids=_journey_ids(journey_ids))


@router.get("/export/{artifact_type}/download")
def export_download(artifact_type: str, journey_ids: str | None = None):
    path, filename, media_type = create_export_file(
        artifact_type,
        GENERATED_DIR,
        journey_ids=_journey_ids(journey_ids),
    )
    return FileResponse(path, filename=filename, media_type=media_type)
