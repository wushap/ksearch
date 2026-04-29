"""System and admin command registration for ksearch CLI."""

import json
import os

import typer
from rich.table import Table

from ksearch.cache import CacheManager
from ksearch.config import expand_path, init_default_config, load_config
from ksearch.embeddings import EmbeddingGenerator
from ksearch.kbase import KnowledgeBase
from ksearch.cli_common import build_stats_table, console, format_size


def register_stats_command(app: typer.Typer) -> None:
    @app.command("stats")
    def stats_cmd(
        store_dir: str = typer.Option("~/.ksearch/store", "--store-dir", "-d", help="Store directory"),
        index_db: str = typer.Option("~/.ksearch/index.db", "--index-db", help="Index database path"),
        kbase_mode: str = typer.Option("chroma", "--kbase-mode", help="kbase mode: chroma or qdrant"),
        kbase_dir: str = typer.Option("~/.ksearch/kbase", "--kbase-dir", help="kbase directory"),
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


def register_config_command(app: typer.Typer) -> None:
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
        config_path = expand_path("~/.ksearch/config.json")

        if init:
            init_default_config(config_path)
            console.print(f"[green]✓[/green] Config initialized at {config_path}")
            return

        if show:
            config = load_config(config_path)
            table = Table(title="Current Configuration")
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="green")
            for key, value in config.items():
                table.add_row(key, str(value))
            console.print(table)
            return

        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as handle:
                config = json.load(handle)

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
            with open(config_path, "w") as handle:
                json.dump(config, handle, indent=2)
            console.print(f"[green]✓[/green] Config updated at {config_path}")
        else:
            console.print("[yellow]No changes[/yellow]")


def register_health_command(app: typer.Typer) -> None:
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

        status = "[green]✓[/green]" if health.get("ollama") else "[red]✗[/red]"
        details = ""
        if health.get("ollama_models"):
            details = f"Models: {', '.join(health['ollama_models'][:3])}"
        if health.get("ollama_error"):
            details = health["ollama_error"]
        table.add_row("Ollama", status, details)

        status = "[green]✓[/green]" if health.get("sentence_transformers") else "[red]✗[/red]"
        table.add_row("Sentence Transformers", status, "Local fallback")
        table.add_row("Simple Embedder", "[green]✓[/green]", "Always available")

        try:
            import requests

            response = requests.get("http://localhost:48888/search?q=test&format=json", timeout=5)
            status = "[green]✓[/green]" if response.status_code == 200 else "[red]✗[/red]"
            table.add_row("SearXNG", status, "http://localhost:48888")
        except Exception as exc:
            table.add_row("SearXNG", "[red]✗[/red]", str(exc)[:30])

        console.print(table)
