"""LangChain tools that expose PowerMem beyond path-keyed file operations.

Deep Agents already maps paths to PowerMem rows via MemoryBackend + PowerMemPathStore.
This module adds tools that use PowerMem's native APIs (e.g. vector search) so the
agent can recall content by meaning, not only by exact path — the main product
differentiator vs plain in-memory or literal grep.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool


def _identity_from_runtime(runtime: ToolRuntime) -> tuple[Any, Any, Any]:
    """Match MemoryBackend identity extraction (user_id falls back to thread_id)."""
    config = getattr(runtime, "config", None) or {}
    if not isinstance(config, dict):
        return None, None, None
    configurable = config.get("configurable", {})
    if not isinstance(configurable, dict):
        return None, None, None
    user_id = configurable.get("user_id") or configurable.get("thread_id")
    agent_id = configurable.get("agent_id")
    run_id = configurable.get("run_id")
    return user_id, agent_id, run_id


def make_powermem_memory_tools(memory: Any) -> list:
    """Build tools bound to a ``powermem.Memory`` instance.

    Args:
        memory: Result of ``powermem.create_memory()``.

    Returns:
        Tools to merge into ``create_deep_agent(..., tools=...)``.
    """

    @tool
    def search_memories(
        query: str,
        runtime: ToolRuntime,
        limit: int = 10,
        threshold: float | None = None,
    ) -> str:
        """Search stored memories by semantic similarity (PowerMem vector / hybrid search).

        Use for fuzzy recall: topics, keywords, or \"something we saved about X\" when the
        path is unknown. Results include paths in metadata when present.

        For exact paths or directory listings, prefer ls, read_file, glob, or grep instead.
        """
        user_id, agent_id, run_id = _identity_from_runtime(runtime)
        kwargs: dict[str, Any] = {
            "query": query,
            "user_id": user_id,
            "agent_id": agent_id,
            "run_id": run_id,
            "limit": limit,
        }
        if threshold is not None:
            kwargs["threshold"] = threshold
        try:
            out = memory.search(**kwargs)
        except Exception as e:
            return f"search_memories failed: {e!s}"
        try:
            return json.dumps(out, ensure_ascii=False, default=str)
        except TypeError:
            return str(out)

    return [search_memories]
