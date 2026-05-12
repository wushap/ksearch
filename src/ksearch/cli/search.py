"""Search command registration for ksearch CLI."""

from typing import Optional

import typer
from rich.panel import Panel

from ksearch.cache import CacheManager
from ksearch.cli_common import (
    build_kbase,
    console,
    kbase_results_to_entries,
    resolve_search_runtime_config,
)
from ksearch.config import DEFAULT_CONFIG, load_config, merge_config
from ksearch.converter import ContentConverter
from ksearch.debug_logging import (
    log_command_failure,
    log_command_start,
    log_command_success,
)
from ksearch.iterative_flow.engine import IterativeSearchEngine
from ksearch.output import format_markdown, format_paths
from ksearch.search import SearchEngine
from ksearch.searxng import SearXNGClient


def register_search_command(app: typer.Typer) -> None:
    """Register the top-level search command."""

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
        no_cache: Optional[bool] = typer.Option(None, "--no-cache/--cache", help="Skip cache and force network"),
        only_cache: Optional[bool] = typer.Option(None, "--only-cache/--no-only-cache", help="Only search cache"),
        kbase_mode: str = typer.Option(None, "--kbase", help="Include kbase search: chroma, qdrant, or none"),
        kbase_dir: str = typer.Option(None, "--kbase-dir", help="Knowledge base directory"),
        qdrant_url: str = typer.Option(None, "--qdrant-url", help="Qdrant URL"),
        embedding_mode: str = typer.Option(None, "--embedding-mode", help="Embedding backend: ollama, sentence-transformers, or simple"),
        embedding_model: str = typer.Option(None, "--embedding-model", help="Embedding model"),
        embedding_dimension: int = typer.Option(None, "--embedding-dimension", help="Embedding dimension"),
        ollama_url: str = typer.Option(None, "--ollama-url", help="Ollama URL"),
        allow_embedding_fallback: Optional[bool] = typer.Option(
            None,
            "--allow-embedding-fallback/--strict-embedding",
            help="Allow fallback to sentence-transformers or simple hash embeddings",
        ),
        iterative: Optional[bool] = typer.Option(None, "--iterative/--no-iterative", help="Enable iterative kbase-first search"),
        hybrid: Optional[bool] = typer.Option(None, "--hybrid/--no-hybrid", help="Enable hybrid BM25+vector search"),
        rerank: Optional[bool] = typer.Option(None, "--rerank/--no-rerank", help="Enable Ollama-based re-ranking"),
        verbose: Optional[bool] = typer.Option(None, "--verbose/--no-verbose", "-v", help="Verbose output"),
    ):
        """Search for keyword in cache, kbase, and/or network."""
        try:
            file_config = load_config("~/.ksearch/config.json")

            cli_args = {}
            if no_cache is not None:
                cli_args["no_cache"] = no_cache
            if only_cache is not None:
                cli_args["only_cache"] = only_cache
            if verbose is not None:
                cli_args["verbose"] = verbose
            if iterative is not None:
                cli_args["iterative_enabled"] = iterative
            if hybrid is not None:
                cli_args["hybrid_search"] = hybrid
            if rerank is not None:
                cli_args["rerank_enabled"] = rerank
            if allow_embedding_fallback is not None:
                cli_args["allow_embedding_fallback"] = allow_embedding_fallback
            optional_values = {
                "format": output_format,
                "time_range": time_range,
                "max_results": max_results,
                "searxng_url": searxng_url,
                "store_dir": store_dir,
                "index_db": index_db,
                "timeout": timeout,
                "kbase_mode": kbase_mode,
                "kbase_dir": kbase_dir,
                "qdrant_url": qdrant_url,
                "embedding_mode": embedding_mode,
                "embedding_model": embedding_model,
                "embedding_dimension": embedding_dimension,
                "ollama_url": ollama_url,
            }
            for key, value in optional_values.items():
                if value is not None:
                    cli_args[key] = value

            config = merge_config(cli_args, file_config, DEFAULT_CONFIG)
            explicit_flags = set()
            if kbase_mode is not None and kbase_mode != "none":
                explicit_flags.add("kbase")
            if iterative is True:
                explicit_flags.add("iterative")
            if rerank is True:
                explicit_flags.add("rerank")
            log_command_start(
                "ksearch.cli.search",
                config_snapshot=config,
                command_context={
                    "keyword": keyword,
                    "format": config["format"],
                    "verbose": config.get("verbose", False),
                    "no_cache": config.get("no_cache", False),
                    "only_cache": config.get("only_cache", False),
                    "only_kbase": config.get("only_kbase", False),
                    "kbase_mode": config.get("kbase_mode"),
                },
            )

            config, capability_degradations = resolve_search_runtime_config(config, explicit_flags)
            cache = CacheManager(config["index_db"], config["store_dir"])
            searxng = SearXNGClient(config["searxng_url"], config["timeout"])
            converter = ContentConverter(config["timeout"])
            engine = SearchEngine(cache, searxng, converter)

            if config.get("verbose", False):
                console.print(Panel(f"Searching: {keyword}", title="ksearch"))
                for degradation in capability_degradations:
                    console.print(
                        f"[yellow]{degradation['feature']} auto-disabled:[/yellow] {degradation['reason']}"
                    )

            iterative_enabled = config.get("iterative_enabled") and not config.get("only_cache", False) and not config.get("only_kbase", False)
            backend_failures = []

            if iterative_enabled:
                kbase_mode_value = config.get("kbase_mode")
                if not kbase_mode_value or kbase_mode_value == "none":
                    message = "Iterative search requires --kbase mode (chroma or qdrant)"
                    console.print(f"[red]{message}[/red]")
                    log_command_failure(
                        "ksearch.cli.search",
                        error=message,
                        summary={"keyword": keyword, "iterative_enabled": iterative_enabled},
                    )
                    raise typer.Exit(1)
                try:
                    kbase = build_kbase(config)
                    iterative_engine = IterativeSearchEngine(kbase, searxng, converter, cache, config)
                    all_results = iterative_engine.search(keyword)
                    if config.get("verbose", False):
                        console.print(f"[green]✓[/green] Iterative search: {len(all_results)} results")
                except Exception as exc:
                    console.print(f"[red]Iterative search error: {exc}[/red]")
                    log_command_failure(
                        "ksearch.cli.search",
                        error=exc,
                        summary={"keyword": keyword, "iterative_enabled": iterative_enabled},
                    )
                    raise typer.Exit(1)
            else:
                all_results = []
                kbase_mode_value = config.get("kbase_mode")
                if kbase_mode_value and kbase_mode_value != "none":
                    try:
                        kbase = build_kbase(config)
                        kbase_results = kbase.search(keyword, top_k=config.get("kbase_top_k", 5))
                        if kbase_results and config.get("verbose", False):
                            console.print(f"[cyan]kbase: {len(kbase_results)} results[/cyan]")
                        all_results.extend(kbase_results_to_entries(kbase_results))
                    except Exception as exc:
                        backend_failures.append({"component": "kbase", "message": str(exc)})
                        if config.get("verbose", False):
                            console.print(f"[yellow]kbase search failed: {exc}[/yellow]")

                if not config.get("only_kbase", False):
                    try:
                        web_results = engine.search(keyword, config)
                        if web_results and config.get("verbose", False):
                            console.print(f"[cyan]Web: {len(web_results)} results[/cyan]")
                        all_results.extend(web_results)
                    except Exception as exc:
                        backend_failures.append({"component": "web", "message": str(exc)})
                        if config.get("verbose", False):
                            console.print(f"[red]Web search error: {exc}[/red]")

            output = format_paths(all_results) if config["format"] == "path" else format_markdown(all_results, keyword)
            console.print(output)

            if config.get("verbose", False):
                console.print(f"[green]✓[/green] Total: {len(all_results)} results")

            summary = {
                "keyword": keyword,
                "result_count": len(all_results),
                "iterative_enabled": iterative_enabled,
                "kbase_mode": config.get("kbase_mode"),
                "format": config["format"],
            }
            context_updates = None
            if backend_failures:
                summary["backend_failures"] = backend_failures
                context_updates = {"backend_failures": backend_failures}
            if capability_degradations:
                summary["capability_degradations"] = capability_degradations
                context_updates = {
                    **(context_updates or {}),
                    "capability_degradations": capability_degradations,
                }

            log_command_success(
                "ksearch.cli.search",
                summary=summary,
                context_updates=context_updates,
            )
        except typer.Exit:
            raise
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            log_command_failure(
                "ksearch.cli.search",
                error=exc,
                summary={"keyword": keyword},
            )
            raise typer.Exit(1)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            log_command_failure(
                "ksearch.cli.search",
                error=exc,
                summary={"keyword": keyword},
            )
            raise typer.Exit(1)
        except Exception as exc:
            log_command_failure(
                "ksearch.cli.search",
                error=exc,
                summary={"keyword": keyword},
            )
            raise


__all__ = ["SearchEngine", "register_search_command"]
