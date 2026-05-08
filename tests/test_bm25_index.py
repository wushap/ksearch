"""Tests for BM25 index module."""

import pytest

from ksearch.knowledge.bm25_index import BM25Index, BM25Result, tokenize


class TestTokenize:
    def test_english_whitespace_split(self):
        tokens = tokenize("hello world python")
        assert tokens == ["hello", "world", "python"]

    def test_english_lowercased(self):
        tokens = tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_cjk_bigrams(self):
        tokens = tokenize("搜索测试")
        assert "搜索" in tokens
        assert "测试" in tokens
        # Also includes sliding bigrams and the full segment
        assert "索测" in tokens
        assert "搜索测试" in tokens

    def test_mixed_cjk_and_latin(self):
        tokens = tokenize("python搜索test")
        assert "python" in tokens
        assert "搜索" in tokens
        assert "test" in tokens

    def test_empty_string(self):
        tokens = tokenize("")
        assert tokens == []

    def test_single_word(self):
        tokens = tokenize("hello")
        assert tokens == ["hello"]


class TestBM25Index:
    def test_build_and_query(self):
        index = BM25Index()
        index.build(
            ids=["1", "2", "3"],
            documents=[
                "Python is a programming language",
                "Rust is a systems language",
                "JavaScript is a web language",
            ],
            metadatas=[{"source": "a"}, {"source": "b"}, {"source": "c"}],
        )
        results = index.query("programming language", top_k=3)
        assert len(results) > 0
        assert results[0].id == "1"

    def test_query_empty_index(self):
        index = BM25Index()
        results = index.query("anything", top_k=5)
        assert results == []

    def test_size(self):
        index = BM25Index()
        assert index.size == 0
        index.build(ids=["1", "2"], documents=["a", "b"])
        assert index.size == 2

    def test_add(self):
        index = BM25Index()
        index.build(ids=["1"], documents=["Python programming"])
        index.add(ids=["2"], documents=["Rust systems"])
        assert index.size == 2

    def test_remove(self):
        index = BM25Index()
        index.build(ids=["1", "2"], documents=["Python", "Rust"])
        index.remove(["1"])
        assert index.size == 1
        results = index.query("Python", top_k=5)
        assert len(results) == 0

    def test_clear(self):
        index = BM25Index()
        index.build(ids=["1"], documents=["test"])
        index.clear()
        assert index.size == 0
        results = index.query("test", top_k=5)
        assert results == []

    def test_query_returns_bm25_result_type(self):
        index = BM25Index()
        index.build(
            ids=["1", "2", "3", "4", "5"],
            documents=[
                "test content for searching",
                "other unrelated text here",
                "another document about something",
                "more random content for filler",
                "unrelated stuff and things",
            ],
            metadatas=[
                {"key": "val"},
                {"key": "val2"},
                {"key": "val3"},
                {"key": "val4"},
                {"key": "val5"},
            ],
        )
        results = index.query("test content", top_k=2)
        assert len(results) >= 1
        assert isinstance(results[0], BM25Result)
        assert results[0].id == "1"
        assert results[0].score > 0

    def test_relevance_ranking(self):
        index = BM25Index()
        index.build(
            ids=["1", "2", "3"],
            documents=[
                "asyncio python async await coroutine",
                "python programming tutorial",
                "rust borrow checker ownership",
            ],
        )
        results = index.query("python async", top_k=3)
        assert results[0].id == "1"

    def test_build_replaces_previous(self):
        index = BM25Index()
        index.build(ids=["1"], documents=["old"])
        index.build(ids=["2", "3"], documents=["new one", "new two"])
        assert index.size == 2
        results = index.query("old", top_k=5)
        assert len(results) == 0
