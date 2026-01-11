"""
Tests for retrieval benchmark tier.

Tests retrieval evaluation with mocked and local fixtures.
"""
import pytest
import tempfile
import json
from pathlib import Path

from benchmarks.tiers.retrieval import (
    RetrievalEvaluator,
    RetrievalDocument,
    RetrievalQuery,
    RetrievalEvaluation,
    load_golden_set,
)


class TestRetrievalDocument:
    """Test RetrievalDocument dataclass."""
    
    def test_basic_document(self):
        """Test creating a document."""
        doc = RetrievalDocument(
            id="doc1",
            content="This is a test document.",
        )
        
        assert doc.id == "doc1"
        assert doc.content == "This is a test document."
        assert doc.metadata == {}
    
    def test_document_with_metadata(self):
        """Test document with metadata."""
        doc = RetrievalDocument(
            id="doc2",
            content="Test",
            metadata={"topic": "testing"},
        )
        
        assert doc.metadata["topic"] == "testing"


class TestRetrievalQuery:
    """Test RetrievalQuery dataclass."""
    
    def test_basic_query(self):
        """Test creating a query."""
        query = RetrievalQuery(
            id="q1",
            query="test query",
            relevant_doc_ids={"doc1", "doc2"},
        )
        
        assert query.id == "q1"
        assert len(query.relevant_doc_ids) == 2


class TestRetrievalEvaluator:
    """Test RetrievalEvaluator."""
    
    def test_initialization(self):
        """Test evaluator initialization."""
        docs = [
            RetrievalDocument(id="d1", content="test"),
            RetrievalDocument(id="d2", content="example"),
        ]
        
        evaluator = RetrievalEvaluator(documents=docs)
        
        assert len(evaluator.documents) == 2
        assert "d1" in evaluator._doc_index
    
    def test_default_retrieval_perfect(self):
        """Test default retrieval with perfect match."""
        docs = [
            RetrievalDocument(id="d1", content="machine learning artificial intelligence"),
            RetrievalDocument(id="d2", content="cooking recipes pasta"),
            RetrievalDocument(id="d3", content="deep learning neural networks"),
        ]
        
        evaluator = RetrievalEvaluator(documents=docs)
        
        # Query should match d1 and d3
        retrieved = evaluator._default_retrieval(
            query="machine learning",
            documents=docs,
            k=2,
        )
        
        assert len(retrieved) == 2
        assert "d1" in retrieved  # Should be top match
    
    def test_evaluate_query_perfect_recall(self):
        """Test query evaluation with perfect recall."""
        docs = [
            RetrievalDocument(id="d1", content="python programming language"),
            RetrievalDocument(id="d2", content="java programming language"),
            RetrievalDocument(id="d3", content="cooking recipes"),
        ]
        
        query = RetrievalQuery(
            id="q1",
            query="programming language",
            relevant_doc_ids={"d1", "d2"},
        )
        
        evaluator = RetrievalEvaluator(documents=docs)
        result = evaluator.evaluate_query(query, k=2)
        
        assert result.query_id == "q1"
        assert result.recall == 1.0  # Found both relevant docs
        assert result.precision == 1.0  # All retrieved are relevant
        assert result.f1_score == 1.0
    
    def test_evaluate_query_partial_recall(self):
        """Test query evaluation with partial recall."""
        docs = [
            RetrievalDocument(id="d1", content="machine learning"),
            RetrievalDocument(id="d2", content="deep learning"),
            RetrievalDocument(id="d3", content="natural language processing"),
            RetrievalDocument(id="d4", content="cooking recipes"),
        ]
        
        query = RetrievalQuery(
            id="q1",
            query="learning",
            relevant_doc_ids={"d1", "d2"},  # Expect d1 and d2
        )
        
        evaluator = RetrievalEvaluator(documents=docs)
        result = evaluator.evaluate_query(query, k=2)
        
        # Should retrieve at least one of the relevant docs
        assert result.recall >= 0.5
        assert 0 <= result.f1_score <= 1.0
    
    def test_evaluate_query_no_relevant(self):
        """Test query with no relevant documents found."""
        docs = [
            RetrievalDocument(id="d1", content="cooking"),
            RetrievalDocument(id="d2", content="recipes"),
        ]
        
        query = RetrievalQuery(
            id="q1",
            query="programming",
            relevant_doc_ids={"d3"},  # Document not in corpus
        )
        
        evaluator = RetrievalEvaluator(documents=docs)
        result = evaluator.evaluate_query(query, k=2)
        
        assert result.recall == 0.0
        assert result.precision >= 0.0  # Can be 0 if nothing matches
    
    def test_evaluate_multiple_queries(self):
        """Test evaluating multiple queries."""
        docs = [
            RetrievalDocument(id="d1", content="python machine learning"),
            RetrievalDocument(id="d2", content="java programming"),
            RetrievalDocument(id="d3", content="cooking pasta"),
        ]
        
        queries = [
            RetrievalQuery(
                id="q1",
                query="python programming",
                relevant_doc_ids={"d1", "d2"},
            ),
            RetrievalQuery(
                id="q2",
                query="cooking",
                relevant_doc_ids={"d3"},
            ),
        ]
        
        evaluator = RetrievalEvaluator(documents=docs)
        results = evaluator.evaluate(queries, k=2)
        
        assert results["total_queries"] == 2
        assert "mean_precision" in results
        assert "mean_recall" in results
        assert "mean_f1" in results
        assert "retrieval_score" in results
        assert len(results["results"]) == 2
    
    def test_evaluate_empty_queries(self):
        """Test evaluation with no queries."""
        evaluator = RetrievalEvaluator(documents=[])
        results = evaluator.evaluate([], k=5)
        
        assert results["total_queries"] == 0
        assert results["mean_precision"] == 0.0
        assert "error" in results
    
    def test_custom_retrieval_function(self):
        """Test with custom retrieval function."""
        docs = [
            RetrievalDocument(id="d1", content="test"),
            RetrievalDocument(id="d2", content="example"),
        ]
        
        # Custom retrieval that always returns d1
        def custom_retrieval(query, documents, k):
            return ["d1"]
        
        evaluator = RetrievalEvaluator(
            documents=docs,
            retrieval_fn=custom_retrieval,
        )
        
        query = RetrievalQuery(
            id="q1",
            query="test",
            relevant_doc_ids={"d1"},
        )
        
        result = evaluator.evaluate_query(query, k=1)
        
        assert result.precision == 1.0
        assert result.recall == 1.0


class TestLoadGoldenSet:
    """Test loading golden dataset."""
    
    def test_load_empty_directory(self):
        """Test loading from empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_dir = Path(tmpdir)
            documents, queries = load_golden_set(golden_dir)
            
            assert len(documents) == 0
            assert len(queries) == 0
    
    def test_load_with_documents_only(self):
        """Test loading with only documents file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_dir = Path(tmpdir)
            
            # Create documents file
            docs_data = [
                {"id": "d1", "content": "Test document", "metadata": {}},
                {"id": "d2", "content": "Another document", "metadata": {"topic": "test"}},
            ]
            with open(golden_dir / "documents.json", "w") as f:
                json.dump(docs_data, f)
            
            documents, queries = load_golden_set(golden_dir)
            
            assert len(documents) == 2
            assert len(queries) == 0
            assert documents[0].id == "d1"
            assert documents[1].metadata["topic"] == "test"
    
    def test_load_with_queries_only(self):
        """Test loading with only queries file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_dir = Path(tmpdir)
            
            # Create queries file
            queries_data = [
                {"id": "q1", "query": "test query", "relevant_doc_ids": ["d1", "d2"], "category": "test"},
            ]
            with open(golden_dir / "queries.json", "w") as f:
                json.dump(queries_data, f)
            
            documents, queries = load_golden_set(golden_dir)
            
            assert len(documents) == 0
            assert len(queries) == 1
            assert queries[0].id == "q1"
            assert len(queries[0].relevant_doc_ids) == 2
    
    def test_load_complete_golden_set(self):
        """Test loading complete golden set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            golden_dir = Path(tmpdir)
            
            # Create both files
            docs_data = [
                {"id": "d1", "content": "Document 1", "metadata": {}},
                {"id": "d2", "content": "Document 2", "metadata": {}},
            ]
            with open(golden_dir / "documents.json", "w") as f:
                json.dump(docs_data, f)
            
            queries_data = [
                {"id": "q1", "query": "Query 1", "relevant_doc_ids": ["d1"], "category": "test"},
            ]
            with open(golden_dir / "queries.json", "w") as f:
                json.dump(queries_data, f)
            
            documents, queries = load_golden_set(golden_dir)
            
            assert len(documents) == 2
            assert len(queries) == 1


class TestRealGoldenSet:
    """Test with the real golden set in benchmarks/goldens/."""
    
    def test_load_real_golden_set(self):
        """Test loading the actual golden set."""
        # Get path to real golden set
        golden_dir = Path(__file__).parent.parent.parent / "benchmarks" / "goldens"
        
        if not golden_dir.exists():
            pytest.skip("Golden set directory not found")
        
        documents, queries = load_golden_set(golden_dir)
        
        # Should have some documents and queries
        assert len(documents) > 0, "No documents in golden set"
        assert len(queries) > 0, "No queries in golden set"
        
        # Verify structure
        for doc in documents:
            assert doc.id
            assert doc.content
        
        for query in queries:
            assert query.id
            assert query.query
            assert len(query.relevant_doc_ids) > 0
    
    def test_evaluate_with_real_golden_set(self):
        """Test evaluation with real golden set."""
        golden_dir = Path(__file__).parent.parent.parent / "benchmarks" / "goldens"
        
        if not golden_dir.exists():
            pytest.skip("Golden set directory not found")
        
        documents, queries = load_golden_set(golden_dir)
        
        if not documents or not queries:
            pytest.skip("Golden set is empty")
        
        evaluator = RetrievalEvaluator(documents=documents)
        results = evaluator.evaluate(queries, k=3)
        
        # Should produce valid results
        assert results["total_queries"] == len(queries)
        assert 0 <= results["mean_precision"] <= 1.0
        assert 0 <= results["mean_recall"] <= 1.0
        assert 0 <= results["mean_f1"] <= 1.0
        assert 0 <= results["retrieval_score"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
