"""kbase subcommand registration for ksearch CLI."""

import os

import typer
from rich.panel import Panel
from rich.table import Table

from ksearch.kbase import KnowledgeBase
from ksearch.config import expand_path
from ksearch.cli_common import console


def _build_explicit_kbase(
    kbase_mode: str,
    kbase_dir: str,
    qdrant_url: str,
    embedding_model: str,
    embedding_dimension: int,
    ollama_url: str,
) -> KnowledgeBase:
    return KnowledgeBase(
        mode=kbase_mode,
        persist_dir=kbase_dir,
        qdrant_url=qdrant_url if kbase_mode == "qdrant" else None,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        ollama_url=ollama_url,
    )


def register_kbase_commands(kbase_app: typer.Typer) -> None:
    """Register knowledge-base subcommands."""

    @kbase_app.command("ingest")
    def kbase_ingest(
        path: str = typer.Argument(..., help="File or directory to ingest"),
        glob_pattern: str = typer.Option("*.md", "--glob", "-g", help="File pattern (for directories)"),
        source: str = typer.Option(None, "--source", "-s", help="Source label (logseq, affine, manual)"),
        recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Recursive search"),
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
        embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Ingest files into kbase."""
        path = expand_path(path)
        kbase = _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        )
        metadata = {"source": source} if source else {}

        if verbose:
            console.print(Panel(f"Ingesting: {path}", title="kbase ingest"))

        try:
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
                console.print(f"[red]Path not found: {path}[/red]")
                raise typer.Exit(1)
            console.print(f"[green]✓[/green] Ingested {chunks} chunks from {path}")
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1)

    @kbase_app.command("query")
    def kbase_query(
        query: str = typer.Argument(..., help="Search query"),
        top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results"),
        source: str = typer.Option(None, "--source", "-s", help="Filter by source"),
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
        embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Semantic search in kbase."""
        kbase = _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        )
        if verbose:
            console.print(Panel(f"kbase Search: {query}", title="kbase search"))
        try:
            results = kbase.search(query, top_k=top_k, filter_source=source)
            if not results:
                console.print("[yellow]No results[/yellow]")
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

            if verbose:
                console.print("\n[dim]Content preview:[/dim]")
                for result in results[:3]:
                    console.print(f"\n[cyan]--- {result.title}[/cyan]")
                    console.print(result.content[:200] + "..." if len(result.content) > 200 else result.content)
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1)

    @kbase_app.command("list")
    def kbase_list(
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
        embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    ):
        """List kbase statistics."""
        kbase = _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        )
        table = Table(title="kbase stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Total entries", str(kbase.count()))
        table.add_row("Mode", kbase_mode)
        table.add_row("Directory", kbase_dir)
        sources = kbase.list_sources()
        table.add_row("Sources", ", ".join(sources) if sources else "N/A")
        console.print(table)

    @kbase_app.command("clear")
    def kbase_clear(
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
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
        _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        ).clear()
        console.print("[green]✓[/green] kbase cleared")

    @kbase_app.command("delete")
    def kbase_delete(
        file_path: str = typer.Argument(..., help="File path to delete"),
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
        qdrant_url: str = typer.Option("http://localhost:6333", "--qdrant-url", help="Qdrant URL"),
        embedding_model: str = typer.Option("nomic-embed-text", "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(768, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option("http://localhost:11434", "--ollama-url", help="Ollama URL"),
    ):
        """Delete entries from a specific file."""
        _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        ).delete_by_file(file_path)
        console.print(f"[green]✓[/green] Deleted entries from {file_path}")

    @kbase_app.command("reset")
    def kbase_reset(
        kbase_mode: str = typer.Option("chroma", "--mode", "-m", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
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
        _build_explicit_kbase(
            kbase_mode,
            kbase_dir,
            qdrant_url,
            embedding_model,
            embedding_dimension,
            ollama_url,
        ).reset()
        console.print("[green]✓[/green] kbase reset")
