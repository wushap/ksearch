"""Shared helpers for ksearch CLI modules."""

from __future__ import annotations

import copy

import requests
from rich.console import Console
from rich.table import Table

from ksearch.embeddings import build_kbase_embedding_function
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
    if not config.get("rerank_enabled", False):
        return None
    try:
        from ksearch.knowledge.reranker import ReRanker
        return ReRanker(
            model_name=config.get("rerank_model"),
            ollama_url=config.get("ollama_url", "http://localhost:11434"),
        )
    except Exception:
        return None


def _probe_kbase_backend(config: dict) -> tuple[bool, str | None]:
    """Return whether the configured kbase backend is available."""
    mode = config.get("kbase_mode")
    if not mode or mode == "none":
        return False, "kbase is disabled"

    if mode == "chroma":
        try:
            import chromadb  # noqa: F401
            return True, None
        except ImportError as exc:
            return False, str(exc)

    if mode == "qdrant":
        qdrant_url = (config.get("qdrant_url") or "http://localhost:6333").rstrip("/")
        try:
            response = requests.get(f"{qdrant_url}/collections", timeout=5)
        except Exception as exc:
            return False, str(exc)
        if response.status_code == 200:
            return True, None
        return False, f"Qdrant returned {response.status_code}: {response.text}"

    return False, f"Unknown kbase mode: {mode}"


def _probe_kbase_embedding(config: dict) -> tuple[bool, str | None]:
    """Return whether the configured embedding path is available."""
    try:
        embed = build_kbase_embedding_function(
            embedding_mode=config.get("embedding_mode", "ollama"),
            embedding_model=config.get("embedding_model", "nomic-embed-text"),
            embedding_dimension=config.get("embedding_dimension", 768),
            ollama_url=config.get("ollama_url", "http://localhost:11434"),
            allow_embedding_fallback=config.get("allow_embedding_fallback", False),
        )
        embed("ksearch capability probe")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _probe_ollama_chat_model(model_name: str, ollama_url: str) -> tuple[bool, str | None]:
    """Return whether the Ollama chat model is available."""
    from ksearch.content_optimization.ollama_client import OllamaChatClient

    health = OllamaChatClient(model=model_name, ollama_url=ollama_url).health_check()
    if not health.get("ollama"):
        return False, health.get("error") or f"Ollama unavailable at {ollama_url}"
    if not health.get("model_available"):
        return False, f"model '{model_name}' not available on Ollama"
    return True, None


def resolve_search_runtime_config(
    config: dict,
    explicit_flags: set[str] | None = None,
) -> tuple[dict, list[dict[str, str]]]:
    """Resolve effective search config by probing optional capabilities."""
    explicit_flags = explicit_flags or set()
    effective = copy.deepcopy(config)
    degradations: list[dict[str, str]] = []

    kbase_requested = bool(effective.get("kbase_mode")) and effective.get("kbase_mode") != "none"
    if kbase_requested:
        backend_ok, backend_reason = _probe_kbase_backend(effective)
        embedding_ok, embedding_reason = _probe_kbase_embedding(effective)
        if not backend_ok or not embedding_ok:
            reason = backend_reason if not backend_ok else embedding_reason
            if "iterative" in explicit_flags:
                raise RuntimeError(f"iterative requires available kbase: {reason}")
            if "kbase" in explicit_flags:
                raise RuntimeError(f"kbase requested via --kbase is unavailable: {reason}")
            degradations.append({"feature": "kbase", "reason": reason or "unavailable"})
            effective["kbase_mode"] = "none"
            effective["iterative_enabled"] = False
            effective["rerank_enabled"] = False
            effective["optimization_enabled"] = False

    iterative_requested = bool(effective.get("iterative_enabled"))
    if iterative_requested and effective.get("kbase_mode") == "none":
        if "iterative" in explicit_flags:
            raise RuntimeError("iterative requires available kbase")
        degradations.append({"feature": "iterative", "reason": "kbase unavailable"})
        effective["iterative_enabled"] = False
        effective["optimization_enabled"] = False

    if effective.get("rerank_enabled") and effective.get("kbase_mode") != "none":
        rerank_ok, rerank_reason = _probe_ollama_chat_model(
            effective.get("rerank_model", "gemma4:e2b"),
            effective.get("ollama_url", "http://localhost:11434"),
        )
        if not rerank_ok:
            if "rerank" in explicit_flags:
                raise RuntimeError(f"rerank requested via --rerank is unavailable: {rerank_reason}")
            degradations.append({"feature": "rerank", "reason": rerank_reason or "unavailable"})
            effective["rerank_enabled"] = False

    optimization_relevant = bool(effective.get("optimization_enabled")) and bool(effective.get("iterative_enabled"))
    if optimization_relevant:
        optimization_ok, optimization_reason = _probe_ollama_chat_model(
            effective.get("optimization_model", "gemma4:e2b"),
            effective.get("ollama_url", "http://localhost:11434"),
        )
        if not optimization_ok:
            degradations.append({"feature": "optimization", "reason": optimization_reason or "unavailable"})
            effective["optimization_enabled"] = False

    return effective, degradations


def build_kbase(config: dict) -> KnowledgeBase:
    """Build a kbase instance from merged config."""
    kbase_mode = config.get("kbase_mode")
    if not kbase_mode or kbase_mode == "none":
        raise ValueError("kbase_mode must be 'chroma' or 'qdrant' to build kbase")
    reranker = _build_reranker(config)
    return KnowledgeBase(
        mode=kbase_mode,
        persist_dir=config.get("kbase_dir", "~/.ksearch/kbase"),
        qdrant_url=config.get("qdrant_url"),
        embedding_mode=config.get("embedding_mode", "ollama"),
        embedding_model=config.get("embedding_model", "nomic-embed-text"),
        embedding_dimension=config.get("embedding_dimension", 768),
        ollama_url=config.get("ollama_url", "http://localhost:11434"),
        allow_embedding_fallback=config.get("allow_embedding_fallback", False),
        reranker=reranker,
        use_hybrid=config.get("hybrid_search", True),
        use_rerank=config.get("rerank_enabled", False),
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
