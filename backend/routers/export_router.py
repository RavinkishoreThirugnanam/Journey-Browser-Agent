from fastapi import APIRouter
from fastapi.responses import FileResponse

from services.artifact_file_service import GENERATED_DIR
from services.export_service import export_artifact

router = APIRouter()


@router.get("/export/{artifact_type}")
def export(artifact_type: str):
    return export_artifact(artifact_type)


@router.get("/export/{artifact_type}/download")
def export_download(artifact_type: str):
    artifact = export_artifact(artifact_type)
    filename = f"{artifact_type}.json"
    path = GENERATED_DIR / filename
    if not path.exists():
        path.write_text(__import__('json').dumps(artifact, indent=2), encoding="utf-8")
    return FileResponse(path, filename=filename, media_type="application/json")
