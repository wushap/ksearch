"""CLI entry point for kb."""

import typer
from rich.console import Console
from rich.panel import Panel

from kb.config import load_config, merge_config, DEFAULT_CONFIG, init_default_config
from kb.cache import CacheManager
from kb.searxng import SearXNGClient
from kb.converter import ContentConverter
from kb.search import SearchEngine
from kb.output import format_markdown, format_paths


app = typer.Typer(
    name="kb",
    help="Personal knowledge base with web search",
)
console = Console()


@app.command()
def search(
    keyword: str,
    format: str = typer.Option(None, "--format", "-f", help="Output format: markdown or path"),
    time_range: str = typer.Option(None, "--time-range", "-t", help="Time range: day/week/month/year"),
    max_results: int = typer.Option(None, "--max-results", "-m", help="Max results"),
    searxng_url: str = typer.Option(None, "--searxng-url", "-s", help="SearXNG URL"),
    store_dir: str = typer.Option(None, "--store-dir", "-d", help="Store directory"),
    index_db: str = typer.Option(None, "--index-db", help="Index database path"),
    timeout: int = typer.Option(None, "--timeout", help="Request timeout"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Skip cache, force network"),
    only_cache: bool = typer.Option(False, "--only-cache", help="Only search cache"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Search for keyword in cache and/or network."""
    # Load config file
    file_config = load_config("~/.kb/config.json")

    # Build CLI args dict (only non-None values)
    cli_args = {}
    if format is not None:
        cli_args["format"] = format
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
    cli_args["no_cache"] = no_cache
    cli_args["only_cache"] = only_cache
    cli_args["verbose"] = verbose

    # Merge configs
    config = merge_config(cli_args, file_config, DEFAULT_CONFIG)

    # Initialize components
    cache = CacheManager(config["index_db"], config["store_dir"])
    searxng = SearXNGClient(config["searxng_url"], config["timeout"])
    converter = ContentConverter(config["timeout"])
    engine = SearchEngine(cache, searxng, converter)

    # Execute search
    if verbose:
        console.print(Panel(f"Searching: {keyword}", title="KB Search"))

    results = engine.search(keyword, config)

    # Output
    if config["format"] == "path":
        output = format_paths(results)
    else:
        output = format_markdown(results, keyword)

    console.print(output)

    if verbose:
        console.print(f"[green]✓[/green] Found {len(results)} results")


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()