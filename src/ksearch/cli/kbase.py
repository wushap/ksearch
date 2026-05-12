"""kbase subcommand registration for ksearch CLI."""

import os
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from ksearch.cli_common import _build_reranker, console
from ksearch.config import DEFAULT_CONFIG, expand_path, load_config, merge_config
from ksearch.debug_logging import (
    log_command_failure,
    log_command_start,
    log_command_success,
)
from ksearch.kbase import KnowledgeBase


def _resolve_kbase_config(overrides: dict[str, object]) -> dict:
    cli_args = {key: value for key, value in overrides.items() if value is not None}
    file_config = load_config("~/.ksearch/config.json")
    return merge_config(cli_args, file_config, DEFAULT_CONFIG)


def _build_explicit_kbase(config: dict) -> KnowledgeBase:
    kbase_mode = config.get("kbase_mode")
    if not kbase_mode or kbase_mode == "none":
        raise ValueError("kbase commands require kbase_mode 'chroma' or 'qdrant'")

    return KnowledgeBase(
        mode=kbase_mode,
        persist_dir=config.get("kbase_dir", "~/.ksearch/kbase"),
        qdrant_url=config.get("qdrant_url") if kbase_mode == "qdrant" else None,
        embedding_mode=config.get("embedding_mode", "ollama"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        embedding_dimension=config.get("embedding_dimension", 768),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
        allow_embedding_fallback=config.get("allow_embedding_fallback", False),
        reranker=_build_reranker(config),
        use_hybrid=config.get("hybrid_search", True),
        use_rerank=config.get("rerank_enabled", False),
    )


def _kbase_debug_config(config: dict) -> dict[str, object]:
    return {
        "kbase_mode": config.get("kbase_mode"),
        "kbase_dir": config.get("kbase_dir"),
        "qdrant_url": config.get("qdrant_url"),
        "embedding_mode": config.get("embedding_mode"),
        "embedding_model": config.get("embedding_model"),
        "embedding_dimension": config.get("embedding_dimension"),
        "ollama_url": config.get("ollama_url"),
        "allow_embedding_fallback": config.get("allow_embedding_fallback"),
        "hybrid_search": config.get("hybrid_search"),
        "rerank_enabled": config.get("rerank_enabled"),
        "rerank_model": config.get("rerank_model"),
    }


def register_kbase_commands(kbase_app: typer.Typer) -> None:
    """Register knowledge-base subcommands."""

    @kbase_app.command("ingest")
    def kbase_ingest(
        path: str = typer.Argument(..., help="File or directory to ingest"),
        glob_pattern: str = typer.Option("*.md", "--glob", "-g", help="File pattern (for directories)"),
        source: str = typer.Option(None, "--source", "-s", help="Source label (logseq, affine, manual)"),
        recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recursive search"),
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
        verbose: Optional[bool] = typer.Option(None, "--verbose/--no-verbose", "-v", help="Verbose output"),
    ):
        """Ingest files into kbase."""
        path = expand_path(path)
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                    "verbose": verbose,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.ingest",
                config_snapshot=_kbase_debug_config(config),
                command_context={
                    "subcommand": "ingest",
                    "path": path,
                    "glob_pattern": glob_pattern,
                    "source": source,
                    "recursive": recursive,
                    "verbose": config.get("verbose", False),
                },
            )
            kbase = _build_explicit_kbase(config)
            metadata = {"source": source} if source else {}

            if config.get("verbose", False):
                console.print(Panel(f"Ingesting: {path}", title="kbase ingest"))

            if os.path.isfile(path):
                chunks = kbase.ingest_file(path, metadata=metadata)
            elif os.path.isdir(path):
                chunks = kbase.ingest_directory(
                    path,
                    glob_pattern=glob_pattern,
                    metadata=metadata,
                    recursive=recursive,
                )
            else:
                message = f"Path not found: {path}"
                console.print(f"[red]{message}[/red]")
                log_command_failure(
                    "ksearch.cli.kbase.ingest",
                    error=message,
                    summary={"subcommand": "ingest", "path": path},
                )
                raise typer.Exit(1)
            console.print(f"[green]✓[/green] Ingested {chunks} chunks from {path}")
            log_command_success(
                "ksearch.cli.kbase.ingest",
                summary={
                    "subcommand": "ingest",
                    "path": path,
                    "chunks": chunks,
                },
            )
        except typer.Exit:
            raise
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.ingest",
                error=exc,
                summary={"subcommand": "ingest", "path": path},
            )
            raise typer.Exit(1)

    @kbase_app.command("query")
    def kbase_query(
        query: str = typer.Argument(..., help="Search query"),
        top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
        source: str = typer.Option(None, "--source", "-s", help="Filter by source"),
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
        verbose: Optional[bool] = typer.Option(None, "--verbose/--no-verbose", "-v", help="Verbose output"),
    ):
        """Semantic search in kbase."""
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                    "verbose": verbose,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.query",
                config_snapshot=_kbase_debug_config(config),
                command_context={
                    "subcommand": "query",
                    "query": query,
                    "top_k": top_k,
                    "source": source,
                    "verbose": config.get("verbose", False),
                },
            )
            kbase = _build_explicit_kbase(config)
            if config.get("verbose", False):
                console.print(Panel(f"kbase Search: {query}", title="kbase search"))
            results = kbase.search(query, top_k=top_k, filter_source=source)
            if not results:
                console.print("[yellow]No results[/yellow]")
                log_command_success(
                    "ksearch.cli.kbase.query",
                    summary={"subcommand": "query", "query": query, "result_count": 0},
                )
                return

            table = Table(title=f"kbase Results ({len(results)})")
            table.add_column("Score", style="cyan")
            table.add_column("Title", style="green")
            table.add_column("Source", style="blue")
            table.add_column("Path", style="dim")
            for result in results:
                table.add_row(
                    f"{result.score:.2f}",
                    result.title or "N/A",
                    result.source or "local",
                    result.file_path[:50] if len(result.file_path) > 50 else result.file_path,
                )
            console.print(table)

            if config.get("verbose", False):
                console.print("\n[dim]Content preview:[/dim]")
                for result in results[:3]:
                    console.print(f"\n[cyan]--- {result.title}[/cyan]")
                    console.print(result.content[:200] + "..." if len(result.content) > 200 else result.content)
            log_command_success(
                "ksearch.cli.kbase.query",
                summary={
                    "subcommand": "query",
                    "query": query,
                    "result_count": len(results),
                },
            )
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.query",
                error=exc,
                summary={"subcommand": "query", "query": query},
            )
            raise typer.Exit(1)

    @kbase_app.command("list")
    def kbase_list(
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
    ):
        """List kbase statistics."""
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.list",
                config_snapshot=_kbase_debug_config(config),
                command_context={"subcommand": "list"},
            )
            kbase = _build_explicit_kbase(config)
            table = Table(title="kbase stats")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            count = kbase.count()
            table.add_row("Total entries", str(count))
            table.add_row("Mode", config.get("kbase_mode", "unknown"))
            table.add_row("Directory", config.get("kbase_dir", "unknown"))
            sources = kbase.list_sources()
            table.add_row("Sources", ", ".join(sources) if sources else "N/A")
            console.print(table)
            log_command_success(
                "ksearch.cli.kbase.list",
                summary={"subcommand": "list", "total_entries": count, "source_count": len(sources)},
            )
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.list",
                error=exc,
                summary={"subcommand": "list"},
            )
            raise typer.Exit(1)

    @kbase_app.command("clear")
    def kbase_clear(
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
        confirm: bool = typer.Option(False, "--confirm", help="Confirm clear"),
    ):
        """Clear kbase."""
        if not confirm:
            message = "Use --confirm to clear"
            console.print(f"[red]{message}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.clear",
                error=message,
                summary={"subcommand": "clear"},
            )
            raise typer.Exit(1)
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.clear",
                config_snapshot=_kbase_debug_config(config),
                command_context={"subcommand": "clear", "confirm": confirm},
            )
            _build_explicit_kbase(config).clear()
            console.print("[green]✓[/green] kbase cleared")
            log_command_success(
                "ksearch.cli.kbase.clear",
                summary={"subcommand": "clear"},
            )
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.clear",
                error=exc,
                summary={"subcommand": "clear"},
            )
            raise typer.Exit(1)

    @kbase_app.command("delete")
    def kbase_delete(
        file_path: str = typer.Argument(..., help="File path to delete"),
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
    ):
        """Delete entries from a specific file."""
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.delete",
                config_snapshot=_kbase_debug_config(config),
                command_context={"subcommand": "delete", "file_path": file_path},
            )
            _build_explicit_kbase(config).delete_by_file(file_path)
            console.print(f"[green]✓[/green] Deleted entries from {file_path}")
            log_command_success(
                "ksearch.cli.kbase.delete",
                summary={"subcommand": "delete", "file_path": file_path},
            )
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.delete",
                error=exc,
                summary={"subcommand": "delete", "file_path": file_path},
            )
            raise typer.Exit(1)

    @kbase_app.command("reset")
    def kbase_reset(
        kbase_mode: str = typer.Option(None, "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(None, "--allow-embedding-fallback/--strict-embedding", help="Allow fallback embeddings instead of fail-fast"),
        confirm: bool = typer.Option(False, "--confirm", help="Confirm kbase reset"),
    ):
        """Reset kbase data after changing embedding settings."""
        if not confirm:
            message = "Use --confirm to reset"
            console.print(f"[red]{message}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.reset",
                error=message,
                summary={"subcommand": "reset"},
            )
            raise typer.Exit(1)
        try:
            config = _resolve_kbase_config(
                {
                    "kbase_mode": kbase_mode,
                    "kbase_dir": kbase_dir,
                    "qdrant_url": qdrant_url,
                    "embedding_mode": embedding_mode,
                    "embedding_model": embedding_model,
                    "embedding_dimension": embedding_dimension,
                    "ollama_url": ollama_url,
                    "allow_embedding_fallback": allow_embedding_fallback,
                }
            )
            log_command_start(
                "ksearch.cli.kbase.reset",
                config_snapshot=_kbase_debug_config(config),
                command_context={"subcommand": "reset", "confirm": confirm},
            )
            _build_explicit_kbase(config).reset()
            console.print("[green]✓[/green] kbase reset")
            log_command_success(
                "ksearch.cli.kbase.reset",
                summary={"subcommand": "reset"},
            )
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            log_command_failure(
                "ksearch.cli.kbase.reset",
                error=exc,
                summary={"subcommand": "reset"},
            )
            raise typer.Exit(1)


__all__ = ["KnowledgeBase", "register_kbase_commands"]
