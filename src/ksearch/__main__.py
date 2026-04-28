"""CLI entry point for ksearch."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ksearch.config import load_config, merge_config, DEFAULT_CONFIG, expand_path
from ksearch.cache import CacheManager
from ksearch.searxng import SearXNGClient
from ksearch.converter import ContentConverter
from ksearch.embeddings import EmbeddingGenerator
from ksearch.search import SearchEngine
from ksearch.output import format_markdown, format_paths
from ksearch.kb import KnowledgeBase
from ksearch.models import ResultEntry


app = typer.Typer(
    name="ksearch",
    help="Personal knowledge base with web search - CLI tool",
)
kb_app = typer.Typer(
    name="kb",
    help="Knowledge base operations",
)
app.add_typer(kb_app, name="kb")

console = Console()


def build_kb(config: dict) -> KnowledgeBase:
    """Build a knowledge base instance from merged config."""
    kb_mode = config.get("kb_mode") or "chroma"
    return KnowledgeBase(
        mode=kb_mode,
        persist_dir=config.get("kb_dir", "~/.ksearch/kb"),
        qdrant_url=config.get("qdrant_url"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
    )


def kb_results_to_entries(results: list) -> list[ResultEntry]:
    """Convert KB search results into output entries."""
    entries = []
    for result in results:
        preview = result.content[:500] + "..." if len(result.content) > 500 else result.content
        entries.append(ResultEntry(
            url=f"kb://{result.id}",
            title=result.title or result.file_path,
            content=preview,
            file_path=result.file_path,
            cached=True,
            source=f"kb:{result.source or 'local'}",
            cached_date=result.metadata.get("created_at", "") if result.metadata else "",
        ))
    return entries


@app.command()
def search(
    keyword: str,
    output_format: str = typer.Option(None, "--format", "-f", help="Output format: markdown or path"),
    time_range: str = typer.Option(None, "--time-range", "-t", help="Time range: day/week/month/year"),
    max_results: int = typer.Option(None, "--max-results", "-m", help="Max results"),
    searxng_url: str = typer.Option(None, "--searxng-url", "-s", help="SearXNG URL"),
    store_dir: str = typer.Option(None, "--store-dir", "-d", help="Store directory"),
    index_db: str = typer.Option(None, "--index-db", help="Index database path"),
    timeout: int = typer.Option(None, "--timeout", help="Request timeout"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache, force network"),
    only_cache: bool = typer.Option(False, "--only-cache", help="Only search cache"),
    kb_mode: str = typer.Option(None, "--kb", help="Include KB search: chroma, qdrant, or none"),
    kb_dir: str = typer.Option(None, "--kb-dir", help="Knowledge base directory"),
    qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    iterative: bool = typer.Option(False, "--iterative", help="Enable iterative KB-first search"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Search for keyword in cache, KB, and/or network."""
    # Load config file
    file_config = load_config("~/.ksearch/config.json")

    # Build CLI args dict (only non-None values)
    cli_args = {}
    if output_format is not None:
        cli_args["format"] = output_format
    if time_range is not None:
        cli_args["time_range"] = time_range
    if max_results is not None:
        cli_args["max_results"] = max_results
    if searxng_url is not None:
        cli_args["searxng_url"] = searxng_url
    if store_dir is not None:
        cli_args["store_dir"] = store_dir
    if index_db is not None:
        cli_args["index_db"] = index_db
    if timeout is not None:
        cli_args["timeout"] = timeout
    if kb_mode is not None:
        cli_args["kb_mode"] = kb_mode
    if kb_dir is not None:
        cli_args["kb_dir"] = kb_dir
    if qdrant_url is not None:
        cli_args["qdrant_url"] = qdrant_url
    cli_args["no_cache"] = no_cache
    cli_args["only_cache"] = only_cache
    cli_args["verbose"] = verbose
    cli_args["iterative_enabled"] = iterative

    # Merge configs
    config = merge_config(cli_args, file_config, DEFAULT_CONFIG)

    # Initialize components
    cache = CacheManager(config["index_db"], config["store_dir"])
    searxng = SearXNGClient(config["searxng_url"], config["timeout"])
    converter = ContentConverter(config["timeout"])
    engine = SearchEngine(cache, searxng, converter)

    if verbose:
        console.print(Panel(f"Searching: {keyword}", title="ksearch"))

    # Iterative KB-first search
    if config.get("iterative_enabled"):
        from ksearch.iterative import IterativeSearchEngine
        kb_mode_value = config.get("kb_mode")
        if not kb_mode_value or kb_mode_value == "none":
            console.print("[red]Iterative search requires --kb mode (chroma or qdrant)[/red]")
            raise typer.Exit(1)
        try:
            kb = build_kb(config)
            iterative_engine = IterativeSearchEngine(kb, searxng, converter, cache, config)
            all_results = iterative_engine.search(keyword)
            if verbose:
                console.print(f"[green]✓[/green] Iterative search: {len(all_results)} results")
        except Exception as e:
            console.print(f"[red]Iterative search error: {e}[/red]")
            raise typer.Exit(1)
    else:
        all_results = []

        # KB search (if enabled)
        kb_mode_value = config.get("kb_mode")
        if kb_mode_value and kb_mode_value != "none":
            try:
                kb = build_kb(config)
                kb_results = kb.search(keyword, top_k=config.get("kb_top_k", 5))

                if kb_results and verbose:
                    console.print(f"[cyan]KB: {len(kb_results)} results[/cyan]")

                all_results.extend(kb_results_to_entries(kb_results))
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]KB search failed: {e}[/yellow]")

        # Web/cache search
        if not config.get("only_kb", False):
            try:
                web_results = engine.search(keyword, config)
                if web_results and verbose:
                    console.print(f"[cyan]Web: {len(web_results)} results[/cyan]")
                all_results.extend(web_results)
            except Exception as e:
                if verbose:
                    console.print(f"[red]Web search error: {e}[/red]")

    # Output
    if config["format"] == "path":
        output = format_paths(all_results)
    else:
        output = format_markdown(all_results, keyword)

    console.print(output)

    if verbose:
        console.print(f"[green]✓[/green] Total: {len(all_results)} results")


# KB subcommands
@kb_app.command("ingest")
def kb_ingest(
    path: str = typer.Argument(..., help="File or directory to ingest"),
    glob_pattern: str = typer.Option("*.md", "--glob", "-g", help="File pattern (for directories)"),
    source: str = typer.Option(None, "--source", "-s", help="Source label (logseq, affine, manual)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recursive search"),
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Ingest files into knowledge base."""
    path = expand_path(path)

    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
    )

    metadata = {}
    if source:
        metadata["source"] = source

    if verbose:
        console.print(Panel(f"Ingesting: {path}", title="kb ingest"))

    try:
        import os
        if os.path.isfile(path):
            chunks = kb.ingest_file(path, metadata=metadata)
            console.print(f"[green]✓[/green] Ingested {chunks} chunks from {path}")
        elif os.path.isdir(path):
            chunks = kb.ingest_directory(
                path,
                glob_pattern=glob_pattern,
                metadata=metadata,
                recursive=recursive,
            )
            console.print(f"[green]✓[/green] Ingested {chunks} chunks from {path}")
        else:
            console.print(f"[red]Path not found: {path}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@kb_app.command("search")
def kb_search(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    source: str = typer.Option(None, "--source", "-s", help="Filter by source"),
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Semantic search in knowledge base."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
    )

    if verbose:
        console.print(Panel(f"KB Search: {query}", title="kb search"))

    try:
        results = kb.search(
            query,
            top_k=top_k,
            filter_source=source,
        )

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        table = Table(title=f"KB Results ({len(results)})")
        table.add_column("Score", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Source", style="blue")
        table.add_column("Path", style="dim")

        for r in results:
            table.add_row(
                f"{r.score:.2f}",
                r.title or "N/A",
                r.source or "local",
                r.file_path[:50] if len(r.file_path) > 50 else r.file_path,
            )

        console.print(table)

        if verbose:
            console.print("\n[dim]Content preview:[/dim]")
            for r in results[:3]:
                console.print(f"\n[cyan]--- {r.title}[/cyan]")
                console.print(r.content[:200] + "..." if len(r.content) > 200 else r.content)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@kb_app.command("list")
def kb_list(
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
):
    """List knowledge base statistics."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
    )

    count = kb.count()
    sources = kb.list_sources()

    table = Table(title="Knowledge Base Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total entries", str(count))
    table.add_row("Mode", kb_mode)
    table.add_row("Directory", kb_dir)
    table.add_row("Sources", ", ".join(sources) if sources else "N/A")

    console.print(table)


@kb_app.command("clear")
def kb_clear(
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm clear"),
):
    """Clear knowledge base."""
    if not confirm:
        console.print("[red]Use --confirm to clear[/red]")
        raise typer.Exit(1)

    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
    )

    kb.clear()
    console.print("[green]✓[/green] Knowledge base cleared")


@kb_app.command("delete")
def kb_delete(
    file_path: str = typer.Argument(..., help="File path to delete"),
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
):
    """Delete entries from a specific file."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
    )

    kb.delete_by_file(file_path)
    console.print(f"[green]✓[/green] Deleted entries from {file_path}")


# Config command
@app.command("config")
def config_cmd(
    init: bool = typer.Option(False, "--init", help="Initialize default config"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
    searxng_url: str = typer.Option(None, "--searxng-url", "-s", help="Set SearXNG URL"),
    kb_mode: str = typer.Option(None, "--kb-mode", help="Set KB mode"),
    kb_dir: str = typer.Option(None, "--kb-dir", help="Set KB directory"),
    ollama_url: str = typer.Option(None, "--ollama-url", help="Set Ollama URL"),
):
    """Manage configuration."""
    config_path = expand_path("~/.ksearch/config.json")

    if init:
        from ksearch.config import init_default_config
        init_default_config(config_path)
        console.print(f"[green]✓[/green] Config initialized at {config_path}")
        return

    if show:
        config = load_config(config_path)
        table = Table(title="Current Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for k, v in config.items():
            table.add_row(k, str(v))
        console.print(table)
        return

    # Update config
    import json
    import os

    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)

    if searxng_url:
        config["searxng_url"] = searxng_url
    if kb_mode:
        config["kb_mode"] = kb_mode
    if kb_dir:
        config["kb_dir"] = kb_dir
    if ollama_url:
        config["ollama_url"] = ollama_url

    if config:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        console.print(f"[green]✓[/green] Config updated at {config_path}")
    else:
        console.print("[yellow]No changes[/yellow]")


# Health check command
@app.command("health")
def health_check(
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """Check health of all services."""
    embedder = EmbeddingGenerator(ollama_url=ollama_url)
    health = embedder.health_check()

    table = Table(title="Service Health")
    table.add_column("Service", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")

    # Ollama
    status = "[green]✓[/green]" if health.get("ollama") else "[red]✗[/red]"
    details = ""
    if health.get("ollama_models"):
        details = f"Models: {', '.join(health['ollama_models'][:3])}"
    if health.get("ollama_error"):
        details = health["ollama_error"]
    table.add_row("Ollama", status, details)

    # Sentence transformers
    status = "[green]✓[/green]" if health.get("sentence_transformers") else "[red]✗[/red]"
    table.add_row("Sentence Transformers", status, "Local fallback")

    # Simple embedder
    table.add_row("Simple Embedder", "[green]✓[/green]", "Always available")

    # Check SearXNG
    try:
        import requests
        response = requests.get("http://localhost:48888/search?q=test&format=json", timeout=5)
        status = "[green]✓[/green]" if response.status_code == 200 else "[red]✗[/red]"
        table.add_row("SearXNG", status, "http://localhost:48888")
    except Exception as e:
        table.add_row("SearXNG", "[red]✗[/red]", str(e)[:30])

    console.print(table)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
