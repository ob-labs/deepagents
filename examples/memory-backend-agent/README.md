# Memory Backend Agent

A minimal **deep agent** example using **Deep Agents + MemoryBackend**: path-keyed memory (PathMemoryStore) instead of the local disk, so the agent has memory and can be extended. Add **PowerMem** for persistence and multi-tenancy.

- For the **Workshop** flow and extension ideas, see [WORKSHOP.md](WORKSHOP.md).
- **Quick-build formula**: deep agent ≈ AGENTS.md (role and path conventions) + MemoryBackend (PowerMem or in-memory) + optional skills/subagents.

## What this demonstrates

- **MemoryBackend** – file operations (ls, read_file, write_file, edit_file, etc.) are backed by a path-keyed store, not disk.
- **PathMemoryStore** – this example uses an in-memory implementation (`store.InMemoryPathStore`). For production you can plug in:
  - **PowerMemPathStore** from `deepagents.backends` with a PowerMem `Memory` instance for persistent, multi-tenant storage.
  - Any custom store that implements the `PathMemoryStore` protocol.

## Quick start

**Three commands to try "paths as memory"** (Workshop step 1):

```bash
python agent.py
python agent.py "Save to /notes/ideas.txt: 1. Learn MemoryBackend 2. Try PowerMem"
python agent.py "List files under /notes/ and read /notes/ideas.txt"
```

With PowerMem, use `python agent_powermem.py "..."` to verify persistence; pass `--user <id>` for multi-tenant isolation (see Run examples below).

### Prerequisites

- Python 3.11+
- **Model API key**: Anthropic (Claude) **or** OpenAI-compatible (e.g. Qwen via DashScope)

### Setup

```bash
cd deepagents/examples/memory-backend-agent
uv sync
# If the venv is not auto-activated: source .venv/bin/activate  (Windows: .venv\Scripts\activate)
cp .env.example .env
# Edit .env: set Deep Agent model (OPENAI_* or ANTHROPIC_API_KEY) and PowerMem required fields (see comments in file)
```

**Faster install**: This directory includes `uv.lock`; `uv sync` installs from the lock file without re-resolving dependencies. If package fetch is slow, use a mirror, e.g.:
```bash
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync
```

**Development from monorepo**: If you cloned the full deepagents repo, the PyPI release may not yet include `MemoryBackend`. Install the local lib first, then run the example:
```bash
cd deepagents/examples/memory-backend-agent
uv sync
uv pip install -e ../../libs/deepagents
python agent.py
```

### Run

**Note:** `agent.py` uses an **in-memory** store. Each `python agent.py` run is a new process, so data saved in one run is not visible in the next. For persistence across runs, use `agent_powermem.py` with PowerMem.

```bash
# Default: list root and describe
python agent.py

# Save a note / list and read (path conventions: /notes/, /tasks/, /reflections/)
# With agent.py, "save" then "list/read" only see the same data if done in the same process (e.g. one Python REPL). For cross-run persistence use agent_powermem.py:
python agent.py "Save to /notes/ideas.txt: 1. Learn MemoryBackend 2. Try PowerMem"
python agent.py "List files under /notes/ and read /notes/ideas.txt"

# Persistent memory (PowerMem): data survives between runs
python agent_powermem.py "Save to /notes/meetup.txt: my notes"
python agent_powermem.py "List files under /notes/ and read /notes/meetup.txt"

# Multi-tenant (with PowerMem): pass --user so each user's memory is isolated
python agent_powermem.py --user alice "Save to /notes/meetup.txt: my notes"
python agent_powermem.py --user bob "List files under /notes/"
```

### With vs without PowerMem

Same two steps — **save**, then in a **new terminal/run** **list and read** — show the difference:

| Step | Without PowerMem (`agent.py`) | With PowerMem (`agent_powermem.py`) |
|------|-------------------------------|-------------------------------------|
| 1. Save | `python agent.py "Save to /notes/ideas.txt: Hello memory"` → “Saved.” | `python agent_powermem.py "Save to /notes/ideas.txt: Hello memory"` → “Saved.” |
| 2. List & read (new run) | `python agent.py "List /notes/ and read /notes/ideas.txt"` → **empty** (new process, in-memory store is fresh) | `python agent_powermem.py "List /notes/ and read /notes/ideas.txt"` → **shows the file and content** (PowerMem persisted it) |

- **Without PowerMem**: store is in-memory only; data is lost when the process exits. Good for trying the API with no setup.
- **With PowerMem**: store is persistent (e.g. SQLite); data survives between runs and can be multi-tenant with `--user`.

## Using PowerMem

PowerMem is included in the project dependencies; `uv sync` installs it. PowerMem runs **in-process** (same process as the agent). There is no separate “PowerMem server” to deploy unless you use PowerMem’s own server mode elsewhere.

### 1. Configure PowerMem

PowerMem reads configuration from a **.env** in the current working directory (or from a config object). Minimum for path-keyed storage:

- **vector_store**: e.g. SQLite (default) or pgvector / OceanBase
- **embedder**: embedding model for the vector store (required by PowerMem)

Configure in `.env` (copy from `.env.example`, which already includes model and PowerMem sections):

```bash
# PowerMem: vector store (SQLite for local dev)
DATABASE_PROVIDER=sqlite
# If using sqlite, optional: DATABASE_PATH=./data/powermem.db

# PowerMem: embedder (e.g. DashScope/Qwen)
EMBEDDING_PROVIDER=qwen
EMBEDDING_API_KEY=your_dashscope_key
EMBEDDING_MODEL=text-embedding-v3
```

PowerMem’s `create_memory()` will load these via `auto_config()`. For PathMemoryStore we call `add(..., infer=False)`, so no LLM is required for plain path-keyed writes; you may still set LLM in .env if PowerMem uses it for other features.

### 2. Wire PowerMem into the agent

Use **PowerMemPathStore** with a PowerMem **Memory** instance:

```python
from deepagents.backends import MemoryBackend, PowerMemPathStore
from powermem import create_memory

memory = create_memory()  # loads from .env
store = PowerMemPathStore(memory)

def backend_factory(runtime):
    return MemoryBackend(store, runtime)

agent = create_deep_agent(..., backend=backend_factory)
```

### 3. Run with PowerMem

After `uv sync` and configuring `.env`, run:

```bash
python agent_powermem.py "Save to /notes/idea.txt: hello PowerMem"
python agent_powermem.py "List files under /notes/ and read /notes/idea.txt"
```

If PowerMem is not configured (e.g. missing or invalid `.env`), `agent_powermem.py` falls back to the in-memory store and prints a short note.

## Project structure

```
memory-backend-agent/
├── agent.py              # Deep Agent with MemoryBackend (in-memory store)
├── agent_powermem.py     # Optional: same agent with PowerMem (or fallback to in-memory)
├── store.py              # InMemoryPathStore for demo (no PowerMem)
├── AGENTS.md             # Agent instructions
├── README.md
├── pyproject.toml
├── uv.lock               # Locked deps (use uv sync for fast install)
├── .env.example          # Unified config template (model + PowerMem); copy to .env to use
└── .gitignore
```

## Requirements

- deepagents >= 0.3.5
- langchain-anthropic >= 1.3.1
- langgraph >= 1.0.6
- python-dotenv >= 1.0.0
- rich >= 13.0.0
