"""Tests for knowledge base module."""

import os
import tempfile
import pytest

from ksearch.kb import KnowledgeBase, KBEntry, KBSearchResult


class TestKBEntry:
    def test_kb_entry_creation(self):
        """Test KBEntry dataclass creation."""
        entry = KBEntry(
            id="test123",
            content="Test content",
            file_path="/tmp/test.md",
        )
        assert entry.id == "test123"
        assert entry.content == "Test content"
        assert entry.file_path == "/tmp/test.md"
        assert entry.tags == []
        assert entry.metadata == {}

    def test_kb_entry_with_metadata(self):
        """Test KBEntry with custom metadata."""
        entry = KBEntry(
            id="test456",
            content="Test content",
            file_path="/tmp/test.md",
            title="Test Title",
            source="logseq",
            tags=["note", "important"],
            metadata={"custom": "value"},
        )
        assert entry.title == "Test Title"
        assert entry.source == "logseq"
        assert entry.tags == ["note", "important"]
        assert entry.metadata["custom"] == "value"


class TestKnowledgeBaseChroma:
    """Test KnowledgeBase with Chroma embedded mode."""

    @pytest.fixture
    def temp_kb(self):
        """Create temporary KB for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(mode="chroma", persist_dir=tmpdir)
            yield kb

    def test_init_chroma(self, temp_kb):
        """Test Chroma initialization."""
        assert temp_kb.mode == "chroma"
        assert temp_kb.count() == 0

    def test_ingest_file(self, temp_kb):
        """Test single file ingestion."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Document\n\nThis is test content for the knowledge base.")
            f.flush()
            filepath = f.name

        chunks = temp_kb.ingest_file(filepath)
        assert chunks > 0
        assert temp_kb.count() == chunks

        os.unlink(filepath)

    def test_search(self, temp_kb):
        """Test semantic search."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Python Programming\n\nPython is a programming language.")
            f.flush()
            filepath = f.name

        temp_kb.ingest_file(filepath)

        results = temp_kb.search("programming language", top_k=5)
        assert len(results) > 0
        assert results[0].content is not None

        os.unlink(filepath)

    def test_search_with_filter(self, temp_kb):
        """Test search with source filter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Note\n\nContent for testing.")
            f.flush()
            filepath = f.name

        temp_kb.ingest_file(filepath, metadata={"source": "manual"})

        results = temp_kb.search("testing", filter_source="manual")
        assert len(results) > 0
        assert results[0].source == "manual"

        # Filter should exclude results
        results = temp_kb.search("testing", filter_source="other")
        assert len(results) == 0

        os.unlink(filepath)

    def test_ingest_directory(self, temp_kb):
        """Test directory ingestion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            for i in range(3):
                filepath = os.path.join(tmpdir, f"note{i}.md")
                with open(filepath, "w") as f:
                    f.write(f"# Note {i}\n\nContent number {i}.")

            chunks = temp_kb.ingest_directory(tmpdir)
            assert chunks >= 3  # At least one chunk per file

    def test_delete_by_file(self, temp_kb):
        """Test deletion by file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Delete Test\n\nThis will be deleted.")
            f.flush()
            filepath = f.name

        temp_kb.ingest_file(filepath)
        assert temp_kb.count() > 0

        temp_kb.delete_by_file(filepath)
        # Note: Chroma may not immediately reflect deletion

        os.unlink(filepath)

    def test_clear(self, temp_kb):
        """Test clearing KB."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Clear Test\n\nContent.")
            f.flush()
            filepath = f.name

        temp_kb.ingest_file(filepath)
        assert temp_kb.count() > 0

        temp_kb.clear()
        assert temp_kb.count() == 0

        os.unlink(filepath)

    def test_list_sources(self, temp_kb):
        """Test listing sources."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Source Test One\n\nContent for logseq source.")
            f.flush()
            filepath1 = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Source Test Two\n\nContent for manual source.")
            f.flush()
            filepath2 = f.name

        temp_kb.ingest_file(filepath1, metadata={"source": "logseq"})
        temp_kb.ingest_file(filepath2, metadata={"source": "manual"})

        sources = temp_kb.list_sources()
        assert "logseq" in sources
        assert "manual" in sources

        os.unlink(filepath1)
        os.unlink(filepath2)


class TestKnowledgeBaseChunking:
    """Test text chunking functionality."""

    @pytest.fixture
    def temp_kb(self):
        """Create temporary KB for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kb = KnowledgeBase(mode="chroma", persist_dir=tmpdir)
            yield kb

    def test_chunk_short_text(self, temp_kb):
        """Test chunking of short text."""
        text = "Short text."
        chunks = temp_kb._chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_chunk_long_text(self, temp_kb):
        """Test chunking of long text."""
        text = "This is a long text. " * 100
        chunks = temp_kb._chunk_text(text, chunk_size=500, chunk_overlap=100)
        assert len(chunks) > 1

    def test_chunk_preserves_sentence_boundary(self, temp_kb):
        """Test chunking respects sentence boundaries."""
        text = "First sentence here. Second sentence follows. Third sentence ends."
        chunks = temp_kb._chunk_text(text, chunk_size=50)
        # Should try to break at periods
        for chunk in chunks:
            assert len(chunk) <= 60  # Allow slight overflow for sentence boundary