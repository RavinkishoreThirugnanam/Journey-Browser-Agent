from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _text(result: Any) -> str:
    parts = []
    for item in getattr(result, 'content', []) or []:
        value = getattr(item, 'text', None)
        if value:
            parts.append(value)
    return '\n'.join(parts)


async def _explore(application_url: str, command: str, args: list[str]) -> dict[str, Any]:
    params = StdioServerParameters(
        command=command,
        args=[str(value) for value in args],
        env={**os.environ, 'PLAYWRIGHT_MCP_SNAPSHOT_MODE': 'full'},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            navigation = await session.call_tool('browser_navigate', {'url': application_url})
            snapshot = await session.call_tool('browser_snapshot', {})
            return {
                'navigation': _text(navigation),
                'snapshot': _text(snapshot),
                'tools': [tool.name for tool in (await session.list_tools()).tools],
            }


def explore_with_mcp(application_url: str, command: str = 'npx', args: list[str] | None = None) -> dict[str, Any]:
    return asyncio.run(_explore(application_url, command, args or ['-y', '@playwright/mcp@latest']))


def snapshot_json(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)
