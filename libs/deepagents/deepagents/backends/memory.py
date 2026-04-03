"""MemoryBackend: Backend that maps file paths to path-keyed memory records.

Uses the PathMemoryStore protocol so any implementation (PowerMem or others) can
be plugged in. Each store record is one "file" with path as the key. This backend
implements BackendProtocol (ls/read/write/edit/glob/grep + upload/download) and
can be used in CompositeBackend routes (e.g. routes={"/memories/": MemoryBackend(store, runtime)}).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    PathMemoryRecord,
    PathMemoryStore,
    WriteResult,
)
from deepagents.backends.utils import (
    _filter_files_by_path,
    _glob_search_files,
    _normalize_path,
    create_file_data,
    format_read_response,
    grep_matches_from_files,
    perform_string_replacement,
)

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime

logger = logging.getLogger(__name__)


def _records_to_files_dict(records: list[PathMemoryRecord]) -> dict[str, dict[str, Any]]:
    """Convert PathMemoryRecord list to path -> FileData dict for utils."""
    return {
        r.path: {
            "content": r.content.split("\n") if r.content else [""],
            "created_at": r.created_at,
            "modified_at": r.modified_at,
        }
        for r in records
    }


class MemoryBackend(BackendProtocol):
    """Backend that stores "files" as path-keyed records via PathMemoryStore.

    Implements BackendProtocol so one store record corresponds to one path.
    Pass any PathMemoryStore implementation (e.g. PowerMemPathStore for PowerMem)
    to support different memory products without binding to one vendor.
    """

    def __init__(self, store: PathMemoryStore, runtime: ToolRuntime) -> None:
        """Initialize MemoryBackend.

        Args:
            store: A PathMemoryStore implementation (e.g. PowerMemPathStore).
            runtime: ToolRuntime for config (user_id, agent_id, run_id from configurable).
        """
        self._store = store
        self.runtime = runtime

    def _get_identity(self) -> tuple[Any, Any, Any]:
        """Get (user_id, agent_id, run_id) from runtime config."""
        config = getattr(self.runtime, "config", None) or {}
        if not isinstance(config, dict):
            return None, None, None
        configurable = config.get("configurable", {})
        if not isinstance(configurable, dict):
            return None, None, None
        user_id = configurable.get("user_id") or configurable.get("thread_id")
        agent_id = configurable.get("agent_id")
        run_id = configurable.get("run_id")
        return user_id, agent_id, run_id

    def _get_record_by_path(self, file_path: str) -> PathMemoryRecord | None:
        """Return the record at path, or None."""
        try:
            norm = _normalize_path(file_path)
        except ValueError:
            return None
        user_id, agent_id, run_id = self._get_identity()
        return self._store.get_by_path(
            norm, user_id=user_id, agent_id=agent_id, run_id=run_id
        )

    def _files_under_path(self, path: str) -> dict[str, dict[str, Any]]:
        """Return path -> FileData for all records under the given path (dir or exact)."""
        user_id, agent_id, run_id = self._get_identity()
        try:
            normalized = _normalize_path(path)
        except ValueError:
            return {}
        records = self._store.list_by_prefix(
            normalized,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
        )
        files = _records_to_files_dict(records)
        return _filter_files_by_path(files, normalized)

    def ls_info(self, path: str) -> list[FileInfo]:
        """List files and directories under path (non-recursive)."""
        infos: list[FileInfo] = []
        subdirs: set[str] = set()
        dir_prefix = path if path.endswith("/") else path + "/"
        if dir_prefix == "//":
            dir_prefix = "/"

        files = self._files_under_path(path)
        for file_path, fd in files.items():
            if not file_path.startswith(dir_prefix) and file_path != _normalize_path(path):
                continue
            rel = file_path[len(dir_prefix):] if file_path.startswith(dir_prefix) else file_path
            if rel.startswith("/"):
                rel = rel[1:]
            if "/" in rel:
                subdir_name = rel.split("/")[0]
                subdirs.add(dir_prefix + subdir_name + "/")
                continue
            if rel:
                size = len("\n".join(fd.get("content", [])))
                infos.append(
                    {
                        "path": file_path,
                        "is_dir": False,
                        "size": int(size),
                        "modified_at": fd.get("modified_at", ""),
                    }
                )

        for subdir in sorted(subdirs):
            infos.append(FileInfo(path=subdir, is_dir=True, size=0, modified_at=""))
        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers (path = one store record)."""
        record = self._get_record_by_path(file_path)
        if record is None:
            return f"Error: File '{file_path}' not found"
        file_data = create_file_data(record.content)
        file_data["created_at"] = record.created_at
        file_data["modified_at"] = record.modified_at
        return format_read_response(file_data, offset, limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Create a new "file" at path; error if path already exists."""
        try:
            norm = _normalize_path(file_path)
        except ValueError as e:
            return WriteResult(error=str(e))
        if self._get_record_by_path(norm) is not None:
            return WriteResult(
                error=f"Cannot write to {norm} because it already exists. Read and then make an edit, or write to a new path."
            )
        user_id, agent_id, run_id = self._get_identity()
        try:
            self._store.add(
                norm,
                content,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
            )
        except Exception as e:
            logger.exception("MemoryBackend.write add failed")
            return WriteResult(error=str(e))
        return WriteResult(path=norm, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit existing record by path (string replace)."""
        record = self._get_record_by_path(file_path)
        if record is None:
            return EditResult(error=f"Error: File '{file_path}' not found")
        result = perform_string_replacement(
            record.content, old_string, new_string, replace_all
        )
        if isinstance(result, str):
            return EditResult(error=result)
        new_content, occurrences = result
        user_id, agent_id, run_id = self._get_identity()
        try:
            self._store.update(
                record.id,
                new_content,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
            )
        except Exception as e:
            logger.exception("MemoryBackend.edit update failed")
            return EditResult(error=str(e))
        return EditResult(path=file_path, files_update=None, occurrences=occurrences)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Literal text search in store contents under path."""
        base = path if path is not None else "/"
        files = self._files_under_path(base)
        return grep_matches_from_files(files, pattern, base, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Return FileInfo for records whose path matches the glob pattern."""
        files = self._files_under_path(path)
        result = _glob_search_files(files, pattern, path)
        if result == "No files found":
            return []
        paths = result.split("\n")
        infos: list[FileInfo] = []
        for p in paths:
            fd = files.get(p)
            if not fd:
                continue
            size = len("\n".join(fd.get("content", [])))
            infos.append(
                {
                    "path": p,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": fd.get("modified_at", ""),
                }
            )
        return infos

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload paths as records (overwrite if path exists)."""
        user_id, agent_id, run_id = self._get_identity()
        responses: list[FileUploadResponse] = []
        for p, raw in files:
            try:
                path_norm = _normalize_path(p)
                content = raw.decode("utf-8", errors="replace")
                existing = self._get_record_by_path(path_norm)
                if existing:
                    self._store.update(
                        existing.id,
                        content,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                    )
                else:
                    self._store.add(
                        path_norm,
                        content,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                    )
                responses.append(FileUploadResponse(path=p, error=None))
            except Exception as e:
                logger.exception("MemoryBackend.upload_files failed for %s", p)
                responses.append(FileUploadResponse(path=p, error="permission_denied"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download store contents by path."""
        responses: list[FileDownloadResponse] = []
        for p in paths:
            record = self._get_record_by_path(p)
            if record is None:
                responses.append(FileDownloadResponse(path=p, content=None, error="file_not_found"))
                continue
            responses.append(
                FileDownloadResponse(path=p, content=record.content.encode("utf-8"), error=None)
            )
        return responses


# ---------------------------------------------------------------------------
# PowerMem implementation of PathMemoryStore (optional dependency)
# ---------------------------------------------------------------------------

PATH_METADATA_KEY = "path"
"""Metadata key for path in PowerMem records (used by PowerMemPathStore)."""

_MEMORY_LIST_LIMIT = 2000


class PowerMemPathStore:
    """PathMemoryStore implementation using PowerMem Memory.

    Use this to plug PowerMem into MemoryBackend. Requires a powermem.Memory
    instance (or compatible add/get/update/delete/get_all API).
    """

    def __init__(self, memory: Any) -> None:
        """Initialize with a PowerMem Memory instance.

        Args:
            memory: powermem.Memory (or compatible) with add, get, update,
                delete, get_all. Path is stored in metadata[path].
        """
        self._memory = memory

    def get_by_path(
        self,
        path: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> PathMemoryRecord | None:
        """Return the record at path, or None."""
        for r in self.list_by_prefix(
            path, user_id=user_id, agent_id=agent_id, run_id=run_id
        ):
            if r.path == path:
                return r
        return None

    def list_by_prefix(
        self,
        prefix: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
        limit: int = _MEMORY_LIST_LIMIT,
    ) -> list[PathMemoryRecord]:
        """Return all records whose path starts with prefix or equals prefix."""
        result = self._memory.get_all(
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            limit=limit,
            offset=0,
        )
        if isinstance(result, dict):
            items = result.get("results", [])
        else:
            items = result if isinstance(result, list) else []
        norm_prefix = prefix.rstrip("/") + "/" if prefix != "/" else "/"
        records: list[PathMemoryRecord] = []
        for m in items:
            meta = m.get("metadata") or {}
            p = meta.get(PATH_METADATA_KEY)
            if not p or not isinstance(p, str) or not p.startswith("/"):
                continue
            if prefix != "/" and not (p == prefix or p.startswith(norm_prefix)):
                continue
            content = m.get("memory") or m.get("content") or ""
            if isinstance(content, list):
                content = "\n".join(content)
            created = m.get("created_at", "")
            updated = m.get("updated_at", "")
            if hasattr(created, "isoformat"):
                created = created.isoformat()
            if hasattr(updated, "isoformat"):
                updated = updated.isoformat()
            records.append(
                PathMemoryRecord(
                    id=m["id"],
                    path=p,
                    content=content,
                    created_at=created,
                    modified_at=updated,
                )
            )
        return records

    def add(
        self,
        path: str,
        content: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> PathMemoryRecord:
        """Create a new record at path."""
        agent_id = agent_id or getattr(self._memory, "agent_id", None)
        metadata = {PATH_METADATA_KEY: path}
        out = self._memory.add(
            content,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            metadata=metadata,
            infer=False,
        )
        if not out or not out.get("results"):
            raise RuntimeError("PowerMem add returned no result")
        res = out["results"][0]
        mid = res.get("id")
        created = res.get("created_at", "")
        if hasattr(created, "isoformat"):
            created = created.isoformat()
        return PathMemoryRecord(
            id=mid,
            path=path,
            content=content,
            created_at=created,
            modified_at=created,
        )

    def update(
        self,
        record_id: Any,
        content: str,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> None:
        """Update record content by id."""
        self._memory.update(
            record_id,
            content,
            user_id=user_id,
            agent_id=agent_id,
        )

    def delete(
        self,
        record_id: Any,
        *,
        user_id: Any = None,
        agent_id: Any = None,
        run_id: Any = None,
    ) -> None:
        """Delete record by id."""
        self._memory.delete(
            record_id,
            user_id=user_id,
            agent_id=agent_id,
        )
