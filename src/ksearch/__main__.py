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


def format_size(num_bytes: int) -> str:
    """Format byte counts for human-readable output."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def build_kb(config: dict) -> KnowledgeBase:
    """Build a knowledge base instance from merged config."""
    kb_mode = config.get("kb_mode") or "chroma"
    return KnowledgeBase(
        mode=kb_mode,
        persist_dir=config.get("kb_dir", "~/.ksearch/kb"),
        qdrant_url=config.get("qdrant_url"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        embedding_dimension=config.get("embedding_dimension", 768),
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


def build_stats_table(title: str, rows: list[tuple[str, str]]) -> Table:
    """Build a two-column stats table."""
    table = Table(title=title)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for metric, value in rows:
        table.add_row(metric, value)
    return table


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
    embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
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
    if embedding_model is not None:
        cli_args["embedding_model"] = embedding_model
    if embedding_dimension is not None:
        cli_args["embedding_dimension"] = embedding_dimension
    if ollama_url is not None:
        cli_args["ollama_url"] = ollama_url
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


@app.command("stats")
def stats_cmd(
    store_dir: str = typer.Option("~/.ksearch/store", "--store-dir", "-d", help="Store directory"),
    index_db: str = typer.Option("~/.ksearch/index.db", "--index-db", help="Index database path"),
    kb_mode: str = typer.Option("chroma", "--kb-mode", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """Show unified cache and knowledge base statistics."""
    cache = CacheManager(expand_path(index_db), expand_path(store_dir))
    cache_stats = cache.stats()

    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )
    kb_stats = kb.stats()

    overview_rows = [
        ("Cache entries", str(cache_stats.get("total_entries", 0))),
        ("KB entries", str(kb_stats.get("total_entries", 0))),
        ("Total knowledge items", str(cache_stats.get("total_entries", 0) + kb_stats.get("total_entries", 0))),
        ("Keyword variety", str(cache_stats.get("keyword_count", 0))),
        ("KB source files", str(kb_stats.get("source_file_count", 0))),
        ("Total size", format_size(cache_stats.get("total_size_bytes", 0) + kb_stats.get("total_size_bytes", 0))),
    ]
    console.print(build_stats_table("Overview", overview_rows))

    cache_rows = [
        ("Entries", str(cache_stats.get("total_entries", 0))),
        ("Keyword count", str(cache_stats.get("keyword_count", 0))),
        ("Total size", format_size(cache_stats.get("total_size_bytes", 0))),
        ("Missing files", str(cache_stats.get("missing_files", 0))),
        ("Top domains", ", ".join(f"{name}:{count}" for name, count in list(cache_stats.get("domains", {}).items())[:5]) or "N/A"),
        ("Engines", ", ".join(f"{name}:{count}" for name, count in list(cache_stats.get("engines", {}).items())[:5]) or "N/A"),
    ]
    console.print(build_stats_table("Cache Stats", cache_rows))

    kb_rows = [
        ("Entries", str(kb_stats.get("total_entries", 0))),
        ("Source files", str(kb_stats.get("source_file_count", 0))),
        ("Total size", format_size(kb_stats.get("total_size_bytes", 0))),
        ("Mode", kb_stats.get("mode", "unknown")),
        ("Embedding model", kb_stats.get("embedding_model", "unknown")),
        ("Embedding dimension", str(kb_stats.get("embedding_dimension", "unknown"))),
        ("Sources", ", ".join(f"{name}:{count}" for name, count in list(kb_stats.get("sources", {}).items())[:5]) or "N/A"),
    ]
    console.print(build_stats_table("Knowledge Base Stats", kb_rows))


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
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Ingest files into knowledge base."""
    path = expand_path(path)

    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
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
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Semantic search in knowledge base."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
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
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """List knowledge base statistics."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
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
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
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
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    kb.clear()
    console.print("[green]✓[/green] Knowledge base cleared")


@kb_app.command("delete")
def kb_delete(
    file_path: str = typer.Argument(..., help="File path to delete"),
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """Delete entries from a specific file."""
    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    kb.delete_by_file(file_path)
    console.print(f"[green]✓[/green] Deleted entries from {file_path}")


@kb_app.command("reset")
def kb_reset(
    kb_mode: str = typer.Option("chroma", "--mode", "-m", help="KB mode: chroma or qdrant"),
    kb_dir: str = typer.Option("~/.ksearch/kb", "--kb-dir", help="KB directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm KB reset"),
):
    """Reset knowledge base data after changing embedding settings."""
    if not confirm:
        console.print("[red]Use --confirm to reset[/red]")
        raise typer.Exit(1)

    kb = KnowledgeBase(
        mode=kb_mode,
        persist_dir=kb_dir,
        qdrant_url=qdrant_url if kb_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )
    kb.reset()
    console.print("[green]✓[/green] Knowledge base reset")


# Config command
@app.command("config")
def config_cmd(
    init: bool = typer.Option(False, "--init", help="Initialize default config"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
    searxng_url: str = typer.Option(None, "--searxng-url", "-s", help="Set SearXNG URL"),
    kb_mode: str = typer.Option(None, "--kb-mode", help="Set KB mode"),
    kb_dir: str = typer.Option(None, "--kb-dir", help="Set KB directory"),
    embedding_model: str = typer.Option(None, "--embedding-model", help="Set embedding model"),
    embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Set embedding dimension"),
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
    if embedding_model:
        config["embedding_model"] = embedding_model
    if embedding_dimension is not None:
        config["embedding_dimension"] = embedding_dimension
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
