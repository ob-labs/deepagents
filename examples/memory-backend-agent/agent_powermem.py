"""Memory Backend Agent with PowerMem (optional).

Uses PowerMem as PathMemoryStore when the package is installed and configured;
otherwise falls back to the in-memory store and prints a short note.
Run with: python agent_powermem.py "your message"
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from rich.console import Console
from rich.panel import Panel

from deepagents import create_deep_agent
from deepagents.backends import MemoryBackend, PowerMemPathStore

from powermem_tools import make_powermem_memory_tools
from store import InMemoryPathStore

load_dotenv()

console = Console()

# Reuse one in-memory store when PowerMem is not used (same process)
_fallback_store: InMemoryPathStore | None = None


def _get_store():
    """Use PowerMem if available and configured, else in-memory store.

    Returns:
        Tuple of (PathMemoryStore, backend label, powermem Memory or None).
    """
    global _fallback_store
    try:
        from powermem import create_memory

        memory = create_memory()
        store = PowerMemPathStore(memory)
        return store, "PowerMem", memory
    except Exception as e:
        hint = ""
        if isinstance(e, ModuleNotFoundError) and e.name == "powermem":
            hint = " Run: uv pip install powermem"
        console.print(
            "[dim]PowerMem not used (install and configure for persistent storage): "
            f"{e!r}. Using in-memory store.{hint}[/dim]\n"
        )
        if _fallback_store is None:
            _fallback_store = InMemoryPathStore()
        return _fallback_store, "in-memory", None


def create_memory_backend_agent():
    """Create a Deep Agent with MemoryBackend (PowerMem or in-memory store)."""
    from agent import _get_model

    _store, store_name, pm_memory = _get_store()
    extra_tools = make_powermem_memory_tools(pm_memory) if pm_memory is not None else []

    def backend_factory(runtime):
        return MemoryBackend(_store, runtime)

    model = _get_model()
    agent = create_deep_agent(
        model=model,
        memory=["./AGENTS.md"],
        skills=[],
        tools=extra_tools,
        subagents=[],
        backend=backend_factory,
    )
    return agent, store_name


def _truncate(text: str, max_len: int = 6000) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n\n[dim]… truncated ({len(text)} chars total)[/dim]"


def _print_tool_trace(messages: list) -> None:
    """Print model tool calls and tool outputs (e.g. search_memories JSON)."""
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if isinstance(tc, dict):
                    name = tc.get("name", "?")
                    args = tc.get("args", {})
                else:
                    name = getattr(tc, "name", "?")
                    args = getattr(tc, "args", {})
                console.print(
                    Panel(
                        f"[bold yellow]Tool call:[/bold yellow] [cyan]{name}[/cyan]\n"
                        f"[dim]{args!r}[/dim]",
                        border_style="yellow",
                        title="tools",
                    )
                )
        elif isinstance(msg, ToolMessage):
            body = msg.content if isinstance(msg.content, str) else repr(msg.content)
            console.print(
                Panel(
                    f"[bold magenta]Tool result[/bold magenta] ([cyan]{msg.name}[/cyan]):\n\n"
                    f"{_truncate(body)}",
                    border_style="magenta",
                    title="tools",
                )
            )


def main():
    parser = argparse.ArgumentParser(
        description="Deep Agent with MemoryBackend (PowerMem or in-memory)",
        epilog="""
Examples:
  python agent_powermem.py "Save to /notes/project.txt: release notes for v1"
  python agent_powermem.py "List files under /notes/ and read /notes/project.txt"
  python agent_powermem.py "What did we save about the release? Use search_memories if helpful."
  python agent_powermem.py -v "What did we save about the release?"   # show tool calls + JSON
  python agent_powermem.py --user bob "Save to /notes/ideas.txt: my ideas"   # multi-tenant
        """,
    )
    parser.add_argument(
        "message",
        type=str,
        nargs="?",
        default="List any files under / and tell me what's there.",
        help="User message",
    )
    parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="User id for multi-tenant isolation (PowerMem)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print tool calls and tool outputs (see search_memories raw JSON, etc.)",
    )
    args = parser.parse_args()

    console.print(
        Panel(f"[bold cyan]Message:[/bold cyan] {args.message}", border_style="cyan")
    )
    console.print()

    console.print("[dim]Creating agent...[/dim]")
    agent, store_name = create_memory_backend_agent()
    tools_note = (
        " + search_memories (semantic)"
        if store_name == "PowerMem"
        else ""
    )
    console.print(f"[dim]Backend: {store_name}{tools_note}[/dim]\n")

    config = {"configurable": {"user_id": args.user}} if args.user else None

    console.print("[dim]Invoking...[/dim]\n")
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.message}]},
            config=config,
        )
        if args.verbose:
            _print_tool_trace(result["messages"])
        final = result["messages"][-1]
        answer = final.content if hasattr(final, "content") else str(final)
        console.print(
            Panel(f"[bold green]Agent:[/bold green]\n\n{answer}", border_style="green")
        )
    except Exception as e:
        console.print(
            Panel(f"[bold red]Error:[/bold red]\n\n{str(e)}", border_style="red")
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
