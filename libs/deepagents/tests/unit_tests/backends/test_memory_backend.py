"""Unit tests for MemoryBackend with an in-memory PathMemoryStore (no PowerMem)."""

from __future__ import annotations

import pytest
from langchain.tools import ToolRuntime
from langgraph.store.memory import InMemoryStore

from deepagents.backends.memory import MemoryBackend
from deepagents.backends.protocol import PathMemoryRecord, PathMemoryStore


class InMemoryPathStore(PathMemoryStore):
    """In-memory PathMemoryStore for testing MemoryBackend without PowerMem."""

    def __init__(self) -> None:
        self._records: dict[str, PathMemoryRecord] = {}
        self._next_id = 0

    def _id(self) -> str:
        self._next_id += 1
        return f"id-{self._next_id}"

    def get_by_path(
        self,
        path: str,
        *,
        user_id: object = None,
        agent_id: object = None,
        run_id: object = None,
    ) -> PathMemoryRecord | None:
        return self._records.get(path)

    def list_by_prefix(
        self,
        prefix: str,
        *,
        user_id: object = None,
        agent_id: object = None,
        run_id: object = None,
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
        user_id: object = None,
        agent_id: object = None,
        run_id: object = None,
    ) -> PathMemoryRecord:
        if path in self._records:
            raise ValueError(f"path already exists: {path}")
        rec = PathMemoryRecord(
            id=self._id(),
            path=path,
            content=content,
            created_at="",
            modified_at="",
        )
        self._records[path] = rec
        return rec

    def update(
        self,
        record_id: object,
        content: str,
        *,
        user_id: object = None,
        agent_id: object = None,
        run_id: object = None,
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
        record_id: object,
        *,
        user_id: object = None,
        agent_id: object = None,
        run_id: object = None,
    ) -> None:
        for path, r in list(self._records.items()):
            if r.id == record_id:
                del self._records[path]
                return
        raise KeyError(record_id)


def make_runtime():
    return ToolRuntime(
        state={"messages": []},
        context=None,
        tool_call_id="t1",
        store=InMemoryStore(),
        stream_writer=lambda _: None,
        config={"configurable": {"user_id": "u1", "agent_id": "a1", "run_id": "r1"}},
    )


def test_memory_backend_write_read_edit_ls_grep_glob():
    from deepagents.backends.protocol import EditResult, WriteResult

    store: PathMemoryStore = InMemoryPathStore()
    rt = make_runtime()
    be = MemoryBackend(store, rt)

    # write new file
    res = be.write("/notes.txt", "hello world")
    assert isinstance(res, WriteResult)
    assert res.error is None and res.path == "/notes.txt"

    # read
    content = be.read("/notes.txt")
    assert "hello world" in content

    # edit
    res2 = be.edit("/notes.txt", "hello", "hi", replace_all=False)
    assert isinstance(res2, EditResult)
    assert res2.error is None and res2.occurrences == 1

    content2 = be.read("/notes.txt")
    assert "hi world" in content2

    # ls_info
    listing = be.ls_info("/")
    assert any(fi["path"] == "/notes.txt" for fi in listing)

    # grep_raw
    matches = be.grep_raw("hi", path="/")
    assert isinstance(matches, list) and any(m["path"] == "/notes.txt" for m in matches)

    # glob_info
    infos = be.glob_info("*.txt", path="/")
    assert any(i["path"] == "/notes.txt" for i in infos)


def test_memory_backend_errors():
    from deepagents.backends.protocol import EditResult, WriteResult

    store: PathMemoryStore = InMemoryPathStore()
    rt = make_runtime()
    be = MemoryBackend(store, rt)

    # edit missing file
    err = be.edit("/missing.txt", "a", "b")
    assert isinstance(err, EditResult) and err.error and "not found" in err.error

    # write then duplicate write
    res = be.write("/dup.txt", "x")
    assert res.error is None
    dup_err = be.write("/dup.txt", "y")
    assert isinstance(dup_err, WriteResult) and dup_err.error and "already exists" in dup_err.error


def test_memory_backend_upload_download():
    store: PathMemoryStore = InMemoryPathStore()
    rt = make_runtime()
    be = MemoryBackend(store, rt)

    # upload
    responses = be.upload_files([("/up.txt", b"uploaded content")])
    assert len(responses) == 1 and responses[0].error is None
    assert "uploaded content" in be.read("/up.txt")

    # download
    downloads = be.download_files(["/up.txt"])
    assert len(downloads) == 1 and downloads[0].error is None and downloads[0].content == b"uploaded content"

    # download missing
    miss = be.download_files(["/nonexistent.txt"])
    assert len(miss) == 1 and miss[0].error == "file_not_found" and miss[0].content is None


def test_memory_backend_ls_nested():
    store: PathMemoryStore = InMemoryPathStore()
    rt = make_runtime()
    be = MemoryBackend(store, rt)

    for path, content in [
        ("/src/main.py", "main"),
        ("/src/utils/helper.py", "helper"),
        ("/docs/readme.md", "readme"),
    ]:
        res = be.write(path, content)
        assert res.error is None

    root = be.ls_info("/")
    paths = [fi["path"] for fi in root]
    assert "/src/" in paths
    assert "/docs/" in paths

    src_list = be.ls_info("/src/")
    assert any(fi["path"] == "/src/main.py" for fi in src_list)
    assert any(fi["path"] == "/src/utils/" for fi in src_list)
