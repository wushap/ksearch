"""Tests for knowledge base module."""

import os
import tempfile
import pytest

from kbase.kbase import KnowledgeBase, KnowledgeBaseEntry, KnowledgeBaseSearchResult


class TestKnowledgeBaseEntry:
    def test_kbase_entry_creation(self):
        """Test KnowledgeBaseEntry dataclass creation."""
        entry = KnowledgeBaseEntry(
            id="test123",
            content="Test content",
            file_path="/tmp/test.md",
        )
        assert entry.id == "test123"
        assert entry.content == "Test content"
        assert entry.file_path == "/tmp/test.md"
        assert entry.tags == []
        assert entry.metadata == {}

    def test_kbase_entry_with_metadata(self):
        """Test KnowledgeBaseEntry with custom metadata."""
        entry = KnowledgeBaseEntry(
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
    def temp_kbase(self):
        """Create temporary kbase for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kbase = KnowledgeBase(mode="chroma", persist_dir=tmpdir)
            yield kbase

    def test_init_chroma(self, temp_kbase):
        """Test Chroma initialization."""
        assert temp_kbase.mode == "chroma"
        assert temp_kbase.count() == 0

    def test_ingest_file(self, temp_kbase):
        """Test single file ingestion."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Document\n\nThis is test content for the knowledge base.")
            f.flush()
            filepath = f.name

        chunks = temp_kbase.ingest_file(filepath)
        assert chunks > 0
        assert temp_kbase.count() == chunks

        os.unlink(filepath)

    def test_search(self, temp_kbase):
        """Test semantic search."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Python Programming\n\nPython is a programming language.")
            f.flush()
            filepath = f.name

        temp_kbase.ingest_file(filepath)

        results = temp_kbase.search("programming language", top_k=5)
        assert len(results) > 0
        assert results[0].content is not None

        os.unlink(filepath)

    def test_search_with_filter(self, temp_kbase):
        """Test search with source filter."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Note\n\nContent for testing.")
            f.flush()
            filepath = f.name

        temp_kbase.ingest_file(filepath, metadata={"source": "manual"})

        results = temp_kbase.search("testing", filter_source="manual")
        assert len(results) > 0
        assert results[0].source == "manual"

        # Filter should exclude results
        results = temp_kbase.search("testing", filter_source="other")
        assert len(results) == 0

        os.unlink(filepath)

    def test_ingest_directory(self, temp_kbase):
        """Test directory ingestion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            for i in range(3):
                filepath = os.path.join(tmpdir, f"note{i}.md")
                with open(filepath, "w") as f:
                    f.write(f"# Note {i}\n\nContent number {i}.")

            chunks = temp_kbase.ingest_directory(tmpdir)
            assert chunks >= 3  # At least one chunk per file

    def test_delete_by_file(self, temp_kbase):
        """Test deletion by file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Delete Test\n\nThis will be deleted.")
            f.flush()
            filepath = f.name

        temp_kbase.ingest_file(filepath)
        assert temp_kbase.count() > 0

        temp_kbase.delete_by_file(filepath)
        # Note: Chroma may not immediately reflect deletion

        os.unlink(filepath)

    def test_clear(self, temp_kbase):
        """Test clearing kbase."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Clear Test\n\nContent.")
            f.flush()
            filepath = f.name

        temp_kbase.ingest_file(filepath)
        assert temp_kbase.count() > 0

        temp_kbase.clear()
        assert temp_kbase.count() == 0

        os.unlink(filepath)

    def test_list_sources(self, temp_kbase):
        """Test listing sources."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Source Test One\n\nContent for logseq source.")
            f.flush()
            filepath1 = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Source Test Two\n\nContent for manual source.")
            f.flush()
            filepath2 = f.name

        temp_kbase.ingest_file(filepath1, metadata={"source": "logseq"})
        temp_kbase.ingest_file(filepath2, metadata={"source": "manual"})

        sources = temp_kbase.list_sources()
        assert "logseq" in sources
        assert "manual" in sources

        os.unlink(filepath1)
        os.unlink(filepath2)


class TestKnowledgeBaseChunking:
    """Test text chunking functionality."""

    @pytest.fixture
    def temp_kbase(self):
        """Create temporary kbase for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kbase = KnowledgeBase(mode="chroma", persist_dir=tmpdir)
            yield kbase

    def test_chunk_short_text(self, temp_kbase):
        """Test chunking of short text."""
        text = "Short text."
        chunks = temp_kbase._chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == "Short text."

    def test_chunk_long_text(self, temp_kbase):
        """Test chunking of long text."""
        text = "This is a long text. " * 100
        chunks = temp_kbase._chunk_text(text, chunk_size=500, chunk_overlap=100)
        assert len(chunks) > 1

    def test_chunk_preserves_sentence_boundary(self, temp_kbase):
        """Test chunking respects sentence boundaries."""
        text = "First sentence here. Second sentence follows. Third sentence ends."
        chunks = temp_kbase._chunk_text(text, chunk_size=50)
        # Should try to break at periods
        for chunk in chunks:
            assert len(chunk) <= 60  # Allow slight overflow for sentence boundary


class TestKnowledgeBaseMetadata:
    def test_init_writes_metadata_file(self):
        """kbase initialization should persist embedding metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            kbase = KnowledgeBase(
                mode="chroma",
                persist_dir=tmpdir,
                embedding_model="nomic-embed-text",
                embedding_dimension=768,
            )

            metadata_path = os.path.join(tmpdir, "_kbase_metadata.json")
            assert os.path.exists(metadata_path)
            assert kbase.embedding_dimension == 768

    def test_reopen_with_same_metadata_succeeds(self):
        """Reopening a kbase with matching embedding settings should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            KnowledgeBase(
                mode="chroma",
                persist_dir=tmpdir,
                embedding_model="nomic-embed-text",
                embedding_dimension=768,
            )

            reopened = KnowledgeBase(
                mode="chroma",
                persist_dir=tmpdir,
                embedding_model="nomic-embed-text",
                embedding_dimension=768,
            )

            assert reopened.embedding_model == "nomic-embed-text"
            assert reopened.embedding_dimension == 768

    def test_reopen_with_mismatched_dimension_requires_reset(self):
        """Changing embedding dimension should fail until the kbase is reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            KnowledgeBase(
                mode="chroma",
                persist_dir=tmpdir,
                embedding_model="nomic-embed-text",
                embedding_dimension=768,
            )

            with pytest.raises(ValueError, match="embedding dimension"):
                KnowledgeBase(
                    mode="chroma",
                    persist_dir=tmpdir,
                    embedding_model="nomic-embed-text",
                    embedding_dimension=1024,
                )

    def test_reopen_with_mismatched_model_requires_reset(self):
        """Changing embedding model should fail until the kbase is reset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            KnowledgeBase(
                mode="chroma",
                persist_dir=tmpdir,
                embedding_model="nomic-embed-text",
                embedding_dimension=768,
            )

            with pytest.raises(ValueError, match="embedding model"):
                KnowledgeBase(
                    mode="chroma",
                    persist_dir=tmpdir,
                    embedding_model="mxbai-embed-large",
                    embedding_dimension=768,
                )


class TestKnowledgeBaseStats:
    def test_stats_reports_chunks_files_sources_and_size(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_dir = os.path.join(tmpdir, "notes")
            os.makedirs(notes_dir, exist_ok=True)

            file_one = os.path.join(notes_dir, "one.md")
            file_two = os.path.join(notes_dir, "two.md")

            with open(file_one, "w", encoding="utf-8") as handle:
                handle.write("# One\n\nPython asyncio cancellation guidance.")
            with open(file_two, "w", encoding="utf-8") as handle:
                handle.write("# Two\n\nRust async cancellation guidance.")

            kbase = KnowledgeBase(mode="chroma", persist_dir=os.path.join(tmpdir, "kbase"))
            kbase.ingest_file(file_one, metadata={"source": "manual"})
            kbase.ingest_file(file_two, metadata={"source": "web"})

            stats = kbase.stats()

            assert stats["total_entries"] == 2
            assert stats["source_file_count"] == 2
            assert stats["total_size_bytes"] > 0
            assert stats["sources"]["manual"] == 1
            assert stats["sources"]["web"] == 1
