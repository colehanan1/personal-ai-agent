"""
Retrieval quality benchmark tier.

Evaluates retrieval quality using a golden dataset of query-document pairs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

logger = logging.getLogger(__name__)


@dataclass
class RetrievalDocument:
    """A document in the retrieval corpus."""
    id: str
    content: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class RetrievalQuery:
    """A retrieval query with expected relevant documents."""
    id: str
    query: str
    relevant_doc_ids: Set[str]  # IDs of documents that should be retrieved
    category: str = "general"


@dataclass
class RetrievalEvaluation:
    """Result of retrieval evaluation."""
    query_id: str
    precision: float
    recall: float
    f1_score: float
    retrieved_doc_ids: List[str]
    relevant_doc_ids: Set[str]
    error: Optional[str] = None


class RetrievalEvaluator:
    """
    Evaluator for retrieval quality.
    
    Measures precision, recall, and F1 score for document retrieval.
    """
    
    def __init__(
        self,
        documents: Optional[List[RetrievalDocument]] = None,
        retrieval_fn: Optional[callable] = None,
    ):
        """
        Initialize retrieval evaluator.
        
        Args:
            documents: List of documents in corpus
            retrieval_fn: Function that takes (query, documents, k) and returns list of doc IDs
        """
        self.documents = documents or []
        self.retrieval_fn = retrieval_fn or self._default_retrieval
        self._doc_index = {doc.id: doc for doc in self.documents}
    
    def _default_retrieval(
        self,
        query: str,
        documents: List[RetrievalDocument],
        k: int = 5,
    ) -> List[str]:
        """
        Default keyword-based retrieval.
        
        Args:
            query: Query string
            documents: List of documents
            k: Number of documents to retrieve
        
        Returns:
            List of retrieved document IDs
        """
        # Simple token overlap scoring
        query_tokens = set(query.lower().split())
        
        scored = []
        for doc in documents:
            doc_tokens = set(doc.content.lower().split())
            overlap = len(query_tokens & doc_tokens)
            score = overlap / max(len(query_tokens), 1)
            scored.append((doc.id, score))
        
        # Sort by score and return top k
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _ in scored[:k]]
    
    def evaluate_query(
        self,
        query: RetrievalQuery,
        k: int = 5,
    ) -> RetrievalEvaluation:
        """
        Evaluate retrieval for a single query.
        
        Args:
            query: Query with expected relevant documents
            k: Number of documents to retrieve
        
        Returns:
            RetrievalEvaluation result
        """
        try:
            # Retrieve documents
            retrieved_ids = self.retrieval_fn(query.query, self.documents, k)
            retrieved_set = set(retrieved_ids)
            relevant_set = query.relevant_doc_ids
            
            # Calculate metrics
            if not retrieved_set:
                precision = 0.0
                recall = 0.0
                f1_score = 0.0
            else:
                true_positives = len(retrieved_set & relevant_set)
                precision = true_positives / len(retrieved_set) if retrieved_set else 0.0
                recall = true_positives / len(relevant_set) if relevant_set else 0.0
                
                if precision + recall > 0:
                    f1_score = 2 * (precision * recall) / (precision + recall)
                else:
                    f1_score = 0.0
            
            return RetrievalEvaluation(
                query_id=query.id,
                precision=precision,
                recall=recall,
                f1_score=f1_score,
                retrieved_doc_ids=retrieved_ids,
                relevant_doc_ids=relevant_set,
            )
        
        except Exception as e:
            logger.error(f"Retrieval evaluation failed for {query.id}: {e}")
            return RetrievalEvaluation(
                query_id=query.id,
                precision=0.0,
                recall=0.0,
                f1_score=0.0,
                retrieved_doc_ids=[],
                relevant_doc_ids=query.relevant_doc_ids,
                error=str(e),
            )
    
    def evaluate(
        self,
        queries: List[RetrievalQuery],
        k: int = 5,
    ) -> Dict[str, Any]:
        """
        Evaluate retrieval for multiple queries.
        
        Args:
            queries: List of queries with expected relevant documents
            k: Number of documents to retrieve
        
        Returns:
            Dictionary with averaged metrics
        """
        if not queries:
            return {
                "mean_precision": 0.0,
                "mean_recall": 0.0,
                "mean_f1": 0.0,
                "total_queries": 0,
                "error": "No queries provided",
            }
        
        results = []
        total_precision = 0.0
        total_recall = 0.0
        total_f1 = 0.0
        
        for query in queries:
            evaluation = self.evaluate_query(query, k=k)
            results.append(evaluation)
            
            if not evaluation.error:
                total_precision += evaluation.precision
                total_recall += evaluation.recall
                total_f1 += evaluation.f1_score
        
        total = len(queries)
        
        return {
            "mean_precision": total_precision / total if total > 0 else 0.0,
            "mean_recall": total_recall / total if total > 0 else 0.0,
            "mean_f1": total_f1 / total if total > 0 else 0.0,
            "retrieval_score": (total_f1 / total * 100) if total > 0 else 0.0,
            "total_queries": total,
            "results": results,
        }


def load_golden_set(golden_dir: Path) -> tuple[List[RetrievalDocument], List[RetrievalQuery]]:
    """
    Load golden retrieval dataset from directory.
    
    Args:
        golden_dir: Directory containing golden set files
    
    Returns:
        Tuple of (documents, queries)
    """
    documents_file = golden_dir / "documents.json"
    queries_file = golden_dir / "queries.json"
    
    documents = []
    queries = []
    
    # Load documents
    if documents_file.exists():
        import json
        with open(documents_file) as f:
            docs_data = json.load(f)
            for doc_data in docs_data:
                documents.append(RetrievalDocument(
                    id=doc_data["id"],
                    content=doc_data["content"],
                    metadata=doc_data.get("metadata", {}),
                ))
    
    # Load queries
    if queries_file.exists():
        import json
        with open(queries_file) as f:
            queries_data = json.load(f)
            for query_data in queries_data:
                queries.append(RetrievalQuery(
                    id=query_data["id"],
                    query=query_data["query"],
                    relevant_doc_ids=set(query_data["relevant_doc_ids"]),
                    category=query_data.get("category", "general"),
                ))
    
    return documents, queries
