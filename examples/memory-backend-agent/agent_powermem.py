"""Memory Backend Agent with PowerMem (optional).

Uses PowerMem as PathMemoryStore when the package is installed and configured;
otherwise falls back to the in-memory store and prints a short note.
Run with: python agent_powermem.py "your message"
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from deepagents import create_deep_agent
from deepagents.backends import MemoryBackend, PowerMemPathStore

from store import InMemoryPathStore

load_dotenv()

console = Console()

# Reuse one in-memory store when PowerMem is not used (same process)
_fallback_store: InMemoryPathStore | None = None


def _get_store():
    """Use PowerMem if available and configured, else in-memory store."""
    global _fallback_store
    try:
        from powermem import create_memory

        memory = create_memory()
        store = PowerMemPathStore(memory)
        return store, "PowerMem"
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
        return _fallback_store, "in-memory"


def create_memory_backend_agent():
    """Create a Deep Agent with MemoryBackend (PowerMem or in-memory store)."""
    from agent import _get_model

    _store, store_name = _get_store()

    def backend_factory(runtime):
        return MemoryBackend(_store, runtime)

    model = _get_model()
    agent = create_deep_agent(
        model=model,
        memory=["./AGENTS.md"],
        skills=[],
        tools=[],
        subagents=[],
        backend=backend_factory,
    )
    return agent, store_name


def main():
    parser = argparse.ArgumentParser(
        description="Deep Agent with MemoryBackend (PowerMem or in-memory)",
        epilog="""
Examples:
  python agent_powermem.py "Save to /notes/meetup.txt: today's workshop notes"
  python agent_powermem.py "List files under /notes/ and read /notes/meetup.txt"
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
    args = parser.parse_args()

    console.print(
        Panel(f"[bold cyan]Message:[/bold cyan] {args.message}", border_style="cyan")
    )
    console.print()

    console.print("[dim]Creating agent...[/dim]")
    agent, store_name = create_memory_backend_agent()
    console.print(f"[dim]Backend: {store_name}[/dim]\n")

    config = {"configurable": {"user_id": args.user}} if args.user else None

    console.print("[dim]Invoking...[/dim]\n")
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.message}]},
            config=config,
        )
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
