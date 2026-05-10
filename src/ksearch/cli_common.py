"""Shared helpers for ksearch CLI modules."""

from rich.console import Console
from rich.table import Table

from ksearch.kbase import KnowledgeBase
from ksearch.models import ResultEntry


console = Console()


def format_size(num_bytes: int) -> str:
    """Format byte counts for human-readable output."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def _build_reranker(config: dict):
    """Build a ReRanker instance when rerank is enabled, or return None."""
    if not config.get("rerank_enabled", True):
        return None
    try:
        from ksearch.knowledge.reranker import ReRanker
        return ReRanker(
            model_name=config.get("rerank_model"),
            ollama_url=config.get("ollama_url", "http://localhost:11434"),
        )
    except Exception:
        return None


def build_kbase(config: dict) -> KnowledgeBase:
    """Build a kbase instance from merged config."""
    kbase_mode = config.get("kbase_mode") or "chroma"
    reranker = _build_reranker(config)
    return KnowledgeBase(
        mode=kbase_mode,
        persist_dir=config.get("kbase_dir", "~/.ksearch/kbase"),
        qdrant_url=config.get("qdrant_url"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        embedding_dimension=config.get("embedding_dimension", 768),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
        reranker=reranker,
        use_hybrid=config.get("hybrid_search", True),
        use_rerank=config.get("rerank_enabled", True),
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
