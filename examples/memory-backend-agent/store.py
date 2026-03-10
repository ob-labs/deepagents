"""In-memory PathMemoryStore for the example (no PowerMem dependency).

For production, replace with PowerMemPathStore(powermem.Memory(...)) or another
PathMemoryStore implementation.
"""

from __future__ import annotations

from typing import Any

from deepagents.backends.protocol import PathMemoryRecord, PathMemoryStore


class InMemoryPathStore(PathMemoryStore):
    """In-memory PathMemoryStore for demos. Data is process-local and not persisted."""

    def __init__(self) -> None:
        self._records: dict[str, PathMemoryRecord] = {}
        self._next_id = 0

    def _new_id(self) -> str:
        self._next_id += 1
        return f"id-{self._next_id}"

    def get_by_path(
        self,
        path: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> PathMemoryRecord | None:
        return self._records.get(path)

    def list_by_prefix(
        self,
        prefix: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
        limit: int = 2000,
    ) -> list[PathMemoryRecord]:
        norm = prefix.rstrip("/") + "/" if prefix != "/" else "/"
        out = []
        for p, r in self._records.items():
            if prefix == "/" or p == prefix or p.startswith(norm):
                out.append(r)
        return out[:limit]

    def add(
        self,
        path: str,
        content: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> PathMemoryRecord:
        if path in self._records:
            raise ValueError(f"path already exists: {path}")
        rec = PathMemoryRecord(
            id=self._new_id(),
            path=path,
            content=content,
            created_at="",
            modified_at="",
        )
        self._records[path] = rec
        return rec

    def update(
        self,
        record_id: Any,
        content: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> None:
        for path, r in list(self._records.items()):
            if r.id == record_id:
                self._records[path] = PathMemoryRecord(
                    id=r.id,
                    path=r.path,
                    content=content,
                    created_at=r.created_at,
                    modified_at="",
                )
                return
        raise KeyError(record_id)

    def delete(
        self,
        record_id: Any,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> None:
        for path, r in list(self._records.items()):
            if r.id == record_id:
                del self._records[path]
                return
        raise KeyError(record_id)
