"""CLI entry point for kbase."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kbase.config import load_config, merge_config, DEFAULT_CONFIG, expand_path
from kbase.cache import CacheManager
from kbase.searxng import SearXNGClient
from kbase.converter import ContentConverter
from kbase.embeddings import EmbeddingGenerator
from kbase.search import SearchEngine
from kbase.output import format_markdown, format_paths
from kbase.kbase import KnowledgeBase
from kbase.models import ResultEntry


app = typer.Typer(
    name="kbase",
    help="Personal knowledge base with web search - CLI tool",
)

console = Console()


def format_size(num_bytes: int) -> str:
    """Format byte counts for human-readable output."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def build_kbase(config: dict) -> KnowledgeBase:
    """Build a kbase instance from merged config."""
    kbase_mode = config.get("kbase_mode") or "chroma"
    return KnowledgeBase(
        mode=kbase_mode,
        persist_dir=config.get("kbase_dir", "~/.kbase/kbase"),
        qdrant_url=config.get("qdrant_url"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        embedding_dimension=config.get("embedding_dimension", 768),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
    )


def kbase_results_to_entries(results: list) -> list[ResultEntry]:
    """Convert kbase search results into output entries."""
    entries = []
    for result in results:
        preview = result.content[:500] + "..." if len(result.content) > 500 else result.content
        entries.append(ResultEntry(
            url=f"kbase://{result.id}",
            title=result.title or result.file_path,
            content=preview,
            file_path=result.file_path,
            cached=True,
            source=f"kbase:{result.source or 'local'}",
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
    kbase_mode: str = typer.Option(None, "--kbase", help="Include kbase search: chroma, qdrant, or none"),
    kbase_dir: str = typer.Option(None, "--kbase-dir", help="Knowledge base directory"),
    qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
    iterative: bool = typer.Option(False, "--iterative", help="Enable iterative kbase-first search"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Search for keyword in cache, kbase, and/or network."""
    # Load config file
    file_config = load_config("~/.kbase/config.json")

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
    if kbase_mode is not None:
        cli_args["kbase_mode"] = kbase_mode
    if kbase_dir is not None:
        cli_args["kbase_dir"] = kbase_dir
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
        console.print(Panel(f"Searching: {keyword}", title="kbase"))

    # Iterative kbase-first search
    if config.get("iterative_enabled"):
        from kbase.iterative import IterativeSearchEngine
        kbase_mode_value = config.get("kbase_mode")
        if not kbase_mode_value or kbase_mode_value == "none":
            console.print("[red]Iterative search requires --kbase mode (chroma or qdrant)[/red]")
            raise typer.Exit(1)
        try:
            kbase = build_kbase(config)
            iterative_engine = IterativeSearchEngine(kbase, searxng, converter, cache, config)
            all_results = iterative_engine.search(keyword)
            if verbose:
                console.print(f"[green]✓[/green] Iterative search: {len(all_results)} results")
        except Exception as e:
            console.print(f"[red]Iterative search error: {e}[/red]")
            raise typer.Exit(1)
    else:
        all_results = []

        # kbase search (if enabled)
        kbase_mode_value = config.get("kbase_mode")
        if kbase_mode_value and kbase_mode_value != "none":
            try:
                kbase = build_kbase(config)
                kbase_results = kbase.search(keyword, top_k=config.get("kbase_top_k", 5))

                if kbase_results and verbose:
                    console.print(f"[cyan]kbase: {len(kbase_results)} results[/cyan]")

                all_results.extend(kbase_results_to_entries(kbase_results))
            except Exception as e:
                if verbose:
                    console.print(f"[yellow]kbase search failed: {e}[/yellow]")

        # Web/cache search
        if not config.get("only_kbase", False):
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
    store_dir: str = typer.Option("~/.kbase/store", "--store-dir", "-d", help="Store directory"),
    index_db: str = typer.Option("~/.kbase/index.db", "--index-db", help="Index database path"),
    kbase_mode: str = typer.Option("chroma", "--kbase-mode", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """Show unified cache and kbase statistics."""
    cache = CacheManager(expand_path(index_db), expand_path(store_dir))
    cache_stats = cache.stats()

    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )
    kbase_stats = kbase.stats()

    overview_rows = [
        ("Cache entries", str(cache_stats.get("total_entries", 0))),
        ("kbase entries", str(kbase_stats.get("total_entries", 0))),
        ("Total knowledge items", str(cache_stats.get("total_entries", 0) + kbase_stats.get("total_entries", 0))),
        ("Keyword variety", str(cache_stats.get("keyword_count", 0))),
        ("kbase source files", str(kbase_stats.get("source_file_count", 0))),
        ("Total size", format_size(cache_stats.get("total_size_bytes", 0) + kbase_stats.get("total_size_bytes", 0))),
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

    kbase_rows = [
        ("Entries", str(kbase_stats.get("total_entries", 0))),
        ("Source files", str(kbase_stats.get("source_file_count", 0))),
        ("Total size", format_size(kbase_stats.get("total_size_bytes", 0))),
        ("Mode", kbase_stats.get("mode", "unknown")),
        ("Embedding model", kbase_stats.get("embedding_model", "unknown")),
        ("Embedding dimension", str(kbase_stats.get("embedding_dimension", "unknown"))),
        ("Sources", ", ".join(f"{name}:{count}" for name, count in list(kbase_stats.get("sources", {}).items())[:5]) or "N/A"),
    ]
    console.print(build_stats_table("kbase stats", kbase_rows))


# kbase data commands
@app.command("ingest")
def kbase_ingest(
    path: str = typer.Argument(..., help="File or directory to ingest"),
    glob_pattern: str = typer.Option("*.md", "--glob", "-g", help="File pattern (for directories)"),
    source: str = typer.Option(None, "--source", "-s", help="Source label (logseq, affine, manual)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recursive search"),
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Ingest files into kbase."""
    path = expand_path(path)

    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    metadata = {}
    if source:
        metadata["source"] = source

    if verbose:
        console.print(Panel(f"Ingesting: {path}", title="kbase ingest"))

    try:
        import os
        if os.path.isfile(path):
            chunks = kbase.ingest_file(path, metadata=metadata)
            console.print(f"[green]✓[/green] Ingested {chunks} chunks from {path}")
        elif os.path.isdir(path):
            chunks = kbase.ingest_directory(
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


@app.command("query")
def kbase_query(
    query: str = typer.Argument(..., help="Search query"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
    source: str = typer.Option(None, "--source", "-s", help="Filter by source"),
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Semantic search in kbase."""
    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    if verbose:
        console.print(Panel(f"kbase Search: {query}", title="kbase search"))

    try:
        results = kbase.search(
            query,
            top_k=top_k,
            filter_source=source,
        )

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        table = Table(title=f"kbase Results ({len(results)})")
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


@app.command("list")
def kbase_list(
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """List kbase statistics."""
    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    count = kbase.count()
    sources = kbase.list_sources()

    table = Table(title="kbase stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total entries", str(count))
    table.add_row("Mode", kbase_mode)
    table.add_row("Directory", kbase_dir)
    table.add_row("Sources", ", ".join(sources) if sources else "N/A")

    console.print(table)


@app.command("clear")
def kbase_clear(
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm clear"),
):
    """Clear kbase."""
    if not confirm:
        console.print("[red]Use --confirm to clear[/red]")
        raise typer.Exit(1)

    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    kbase.clear()
    console.print("[green]✓[/green] kbase cleared")


@app.command("delete")
def kbase_delete(
    file_path: str = typer.Argument(..., help="File path to delete"),
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
):
    """Delete entries from a specific file."""
    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )

    kbase.delete_by_file(file_path)
    console.print(f"[green]✓[/green] Deleted entries from {file_path}")


@app.command("reset")
def kbase_reset(
    kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
    kbase_dir: str = typer.Option("~/.kbase/kbase", "--kbase-dir", help="kbase directory"),
    qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
    embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
    embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
    ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    confirm: bool = typer.Option(False, "--confirm", help="Confirm kbase reset"),
):
    """Reset kbase data after changing embedding settings."""
    if not confirm:
        console.print("[red]Use --confirm to reset[/red]")
        raise typer.Exit(1)

    kbase = KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )
    kbase.reset()
    console.print("[green]✓[/green] kbase reset")


# Config command
@app.command("config")
def config_cmd(
    init: bool = typer.Option(False, "--init", help="Initialize default config"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
    searxng_url: str = typer.Option(None, "--searxng-url", "-s", help="Set SearXNG URL"),
    kbase_mode: str = typer.Option(None, "--kbase-mode", help="Set kbase mode"),
    kbase_dir: str = typer.Option(None, "--kbase-dir", help="Set kbase directory"),
    embedding_model: str = typer.Option(None, "--embedding-model", help="Set embedding model"),
    embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Set embedding dimension"),
    ollama_url: str = typer.Option(None, "--ollama-url", help="Set Ollama URL"),
):
    """Manage configuration."""
    config_path = expand_path("~/.kbase/config.json")

    if init:
        from kbase.config import init_default_config
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
    if kbase_mode:
        config["kbase_mode"] = kbase_mode
    if kbase_dir:
        config["kbase_dir"] = kbase_dir
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
