"""Optimize command registration for ksearch CLI."""

import os

import typer
from rich.panel import Panel

from ksearch.cli_common import console
from ksearch.config import DEFAULT_CONFIG, load_config, merge_config
from ksearch.content_optimization import ContentOptimizer, OllamaChatClient, QualityEvaluator
from ksearch.converter import ContentConverter
from ksearch.debug_logging import (
    log_command_failure,
    log_command_start,
    log_command_success,
)
from ksearch.models import ResultEntry
from ksearch.search import SearchEngine
from ksearch.searxng import SearXNGClient


def register_optimize_command(app: typer.Typer) -> None:
    """Register the optimize command."""

    @app.command()
    def optimize(
        query: str = typer.Argument(..., help="Search query to optimize results for"),
        model: str = typer.Option(None, "--model", help="Ollama model for optimization"),
        max_iterations: int = typer.Option(None, "--max-iterations", "-i", help="Max refinement iterations"),
        confidence: float = typer.Option(None, "--confidence", "-c", help="Quality confidence threshold"),
        temperature: float = typer.Option(None, "--temperature", help="LLM temperature"),
        file_path: str = typer.Option(None, "--file", help="Optimize a local file instead of searching"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Optimize search results using AI iterative refinement."""
        file_config = load_config("~/.ksearch/config.json")

        cli_args = {"optimization_enabled": True, "verbose": verbose}
        optional_values = {
            "optimization_model": model,
            "optimization_max_iterations": max_iterations,
            "optimization_confidence_threshold": confidence,
            "optimization_temperature": temperature,
        }
        for key, value in optional_values.items():
            if value is not None:
                cli_args[key] = value

        config = merge_config(cli_args, file_config, DEFAULT_CONFIG)
        log_command_start(
            "ksearch.cli.optimize",
            config_snapshot=config,
            command_context={
                "query": query,
                "file_path": file_path,
                "verbose": verbose,
            },
        )

        ollama_url = config.get("ollama_url", "http://localhost:11434")
        opt_model = config.get("optimization_model", "gemma4:e2b")
        opt_temperature = config.get("optimization_temperature", 0.3)

        try:
            client = OllamaChatClient(
                model=opt_model,
                ollama_url=ollama_url,
                temperature=opt_temperature,
            )

            health = client.health_check()
            if not health["ollama"]:
                message = health.get("error") or f"Ollama not available at {ollama_url}"
                console.print(f"[red]Ollama not available at {ollama_url}[/red]")
                if health.get("error"):
                    console.print(f"[red]  Error: {health['error']}[/red]")
                log_command_failure(
                    "ksearch.cli.optimize",
                    error=message,
                    summary={"query": query, "file_path": file_path},
                )
                raise typer.Exit(1)
            if not health["model_available"]:
                message = f"Model '{opt_model}' not found on Ollama"
                console.print(f"[red]{message}[/red]")
                console.print(f"[yellow]Pull it with: ollama pull {opt_model}[/yellow]")
                if health.get("available_models"):
                    console.print(f"[dim]Available: {', '.join(health['available_models'][:5])}[/dim]")
                log_command_failure(
                    "ksearch.cli.optimize",
                    error=message,
                    summary={"query": query, "file_path": file_path},
                )
                raise typer.Exit(1)

            evaluator = QualityEvaluator(
                client=client,
                confidence_threshold=config.get("optimization_confidence_threshold", 0.8),
            )
            optimizer = ContentOptimizer(evaluator=evaluator, client=client, config=config)

            if verbose:
                console.print(Panel(f"Optimizing: {query}", title="content-optimization"))
                console.print(f"[dim]Model: {opt_model}, threshold: {config.get('optimization_confidence_threshold', 0.8)}[/dim]")

            if file_path:
                if not os.path.exists(file_path):
                    message = f"File not found: {file_path}"
                    console.print(f"[red]{message}[/red]")
                    log_command_failure(
                        "ksearch.cli.optimize",
                        error=message,
                        summary={"query": query, "file_path": file_path},
                    )
                    raise typer.Exit(1)
                with open(file_path) as f:
                    content = f.read()
                result = optimizer.optimize_content(query, content)
            else:
                from ksearch.cache import CacheManager

                searxng = SearXNGClient(config["searxng_url"], config["timeout"])
                converter = ContentConverter(config["timeout"])
                cache = CacheManager(config["index_db"], config["store_dir"])
                engine = SearchEngine(cache, searxng, converter)

                def search_fn(q: str) -> list[ResultEntry]:
                    try:
                        return engine.search(q, config)
                    except Exception as exc:
                        if verbose:
                            console.print(f"[yellow]Search error for '{q}': {exc}[/yellow]")
                        return []

                result = optimizer.optimize(query, search_fn)

            if verbose:
                console.print(f"\n[green]Optimization complete[/green]")
                console.print(f"[dim]Iterations: {result.iterations_used}, Time: {result.elapsed_seconds:.1f}s[/dim]")
                console.print(f"[dim]Final confidence: {result.quality.confidence:.2f}, Action: {result.quality.action}[/dim]")
                if result.quality.gaps:
                    console.print(f"[dim]Remaining gaps: {', '.join(result.quality.gaps)}[/dim]")

            console.print(result.final_content)
            log_command_success(
                "ksearch.cli.optimize",
                summary={
                    "query": query,
                    "file_path": file_path,
                    "iterations_used": result.iterations_used,
                    "elapsed_seconds": result.elapsed_seconds,
                    "confidence": result.quality.confidence,
                    "action": result.quality.action,
                },
            )
        except typer.Exit:
            raise
        except Exception as exc:
            log_command_failure(
                "ksearch.cli.optimize",
                error=exc,
                summary={"query": query, "file_path": file_path},
            )
            raise
