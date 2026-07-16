import json
from pathlib import Path
from uuid import uuid4

from core.config import STORAGE_DIR


GENERATED_DIR = STORAGE_DIR / "generated_files"


def _ensure_dir() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def write_text_file(filename: str, content: str) -> Path:
    _ensure_dir()
    path = GENERATED_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path


def write_json_file(filename: str, payload) -> Path:
    _ensure_dir()
    path = GENERATED_DIR / filename
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def unique_filename(prefix: str, suffix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}{suffix}"


def write_markdown_file(filename: str, content: str) -> Path:
    _ensure_dir()
    path = GENERATED_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path
