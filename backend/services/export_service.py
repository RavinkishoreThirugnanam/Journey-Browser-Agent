import json

from core.config import STORAGE_DIR


def export_artifact(artifact_type: str) -> dict:
    mapping = {
        "journeys": STORAGE_DIR / "journeys.json",
        "configurations": STORAGE_DIR / "configurations.json",
        "user-stories": STORAGE_DIR / "user_stories.json",
        "test-cases": STORAGE_DIR / "test_cases.json",
        "test-scripts": STORAGE_DIR / "test_scripts.json",
    }
    path = mapping.get(artifact_type)
    if not path or not path.exists():
        return {"artifact_type": artifact_type, "items": []}
    raw = path.read_text(encoding="utf-8")
    return {"artifact_type": artifact_type, "items": json.loads(raw) if raw.strip() else []}
