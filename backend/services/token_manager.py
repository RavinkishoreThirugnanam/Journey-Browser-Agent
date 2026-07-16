from __future__ import annotations

import os
from functools import lru_cache


class TokenManager:
    def __init__(self) -> None:
        self._cached_token: str | None = None

    @lru_cache(maxsize=1)
    def get_valid_token(self) -> str:
        token = (
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENAI_AUTH_TOKEN")
            or os.environ.get("LLM_AUTH_TOKEN")
            or os.environ.get("AUTH_TOKEN")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_TOKEN")
            or ""
        ).strip()
        if not token:
            raise RuntimeError("No OpenAI token found. Set OPENAI_API_KEY or OPENAI_API_TOKEN.")
        self._cached_token = token
        return token
