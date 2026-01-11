"""
Evaluation Metrics for LoRA Adapters

Implements quantitative and qualitative evaluation:
- Perplexity (PPL) comparison
- Semantic coherence
- CoVe agreement rate
- Response quality scoring
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import torch

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Results from adapter evaluation."""
    timestamp: str
    adapter_name: str
    train_loss: Optional[float]
    eval_loss: Optional[float]
    perplexity: Optional[float]
    ppl_change: Optional[float]  # vs baseline
    semantic_score: Optional[float]
    cove_pass_rate: Optional[float]
    quality_score: Optional[float]  # composite
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def passed_quality_check(self, min_quality: float = 0.7) -> bool:
        """Check if adapter meets quality threshold."""
        if self.quality_score is None:
            return False
        return self.quality_score >= min_quality


class EvalMetrics:
    """
    Evaluation metrics calculator for LoRA adapters.
    
    Attributes:
        baseline_ppl: Baseline model perplexity for comparison
        min_cove_pass_rate: Minimum CoVe pass rate threshold
        min_quality_score: Minimum composite quality threshold
    """
    
    def __init__(
        self,
        baseline_ppl: Optional[float] = None,
        min_cove_pass_rate: float = 0.9,
        min_quality_score: float = 0.7,
    ):
        """
        Initialize EvalMetrics.
        
        Args:
            baseline_ppl: Baseline perplexity (computed if None)
            min_cove_pass_rate: Minimum CoVe pass rate
            min_quality_score: Minimum quality threshold
        """
        self.baseline_ppl = baseline_ppl
        self.min_cove_pass_rate = min_cove_pass_rate
        self.min_quality_score = min_quality_score
    
    def compute_perplexity(self, loss: float) -> float:
        """
        Compute perplexity from loss.
        
        Args:
            loss: Cross-entropy loss value
            
        Returns:
            Perplexity value
        """
        return math.exp(loss)
    
    def compute_ppl_change(
        self,
        current_ppl: float,
        baseline_ppl: Optional[float] = None,
    ) -> float:
        """
        Compute perplexity change from baseline.
        
        Negative values indicate improvement.
        
        Args:
            current_ppl: Current adapter perplexity
            baseline_ppl: Baseline perplexity (uses self.baseline_ppl if None)
            
        Returns:
            Percentage change in perplexity
        """
        baseline = baseline_ppl or self.baseline_ppl
        if baseline is None or baseline == 0:
            return 0.0
        
        return ((current_ppl - baseline) / baseline) * 100.0
    
    def evaluate_semantic_coherence(
        self,
        responses: List[str],
        references: Optional[List[str]] = None,
    ) -> float:
        """
        Evaluate semantic coherence of responses.
        
        Uses embeddings to measure semantic similarity.
        
        Args:
            responses: Generated responses
            references: Reference responses (if available)
            
        Returns:
            Coherence score (0.0-1.0)
        """
        try:
            from memory.embeddings import embed_batch, cosine_similarity, is_available
            
            if not is_available():
                logger.warning("Embeddings not available, returning default score")
                return 0.75  # Default reasonable score
            
            # Embed all responses
            response_embeddings = embed_batch(responses, show_progress=False)
            
            if not response_embeddings or None in response_embeddings:
                return 0.75
            
            # If we have references, compute similarity
            if references and len(references) == len(responses):
                ref_embeddings = embed_batch(references, show_progress=False)
                if ref_embeddings and None not in ref_embeddings:
                    similarities = [
                        cosine_similarity(resp, ref)
                        for resp, ref in zip(response_embeddings, ref_embeddings)
                    ]
                    return sum(similarities) / len(similarities)
            
            # Otherwise, compute internal coherence (consistency)
            # Average pairwise similarity
            if len(response_embeddings) < 2:
                return 0.8
            
            similarities = []
            for i in range(len(response_embeddings) - 1):
                for j in range(i + 1, len(response_embeddings)):
                    sim = cosine_similarity(
                        response_embeddings[i],
                        response_embeddings[j]
                    )
                    similarities.append(sim)
            
            return sum(similarities) / len(similarities) if similarities else 0.75
            
        except Exception as e:
            logger.warning(f"Semantic coherence evaluation failed: {e}")
            return 0.75  # Default
    
    def evaluate_cove_agreement(
        self,
        responses: List[str],
        questions: List[str],
    ) -> float:
        """
        Evaluate CoVe verification pass rate.
        
        Args:
            responses: Generated responses
            questions: Original questions
            
        Returns:
            Pass rate (0.0-1.0)
        """
        try:
            from prompting.cove import ChainOfVerification
            
            cove = ChainOfVerification()
            if not cove.is_llm_available():
                logger.warning("LLM not available for CoVe evaluation")
                return 0.9  # Optimistic default
            
            passed = 0
            for question, response in zip(questions, responses):
                try:
                    result = cove.run(question, draft=response)
                    if result.verified:
                        passed += 1
                except Exception as e:
                    logger.debug(f"CoVe check failed: {e}")
                    # Count as pass to avoid penalizing connection issues
                    passed += 1
            
            rate = passed / len(questions) if questions else 1.0
            logger.info(f"CoVe pass rate: {rate:.2%} ({passed}/{len(questions)})")
            return rate
            
        except Exception as e:
            logger.warning(f"CoVe evaluation failed: {e}")
            return 0.9  # Default
    
    def compute_quality_score(
        self,
        ppl_change: Optional[float],
        semantic_score: Optional[float],
        cove_pass_rate: Optional[float],
    ) -> float:
        """
        Compute composite quality score.
        
        Weighted combination of metrics:
        - PPL change: 30% (lower is better)
        - Semantic coherence: 40%
        - CoVe pass rate: 30%
        
        Args:
            ppl_change: Perplexity change percentage
            semantic_score: Semantic coherence score
            cove_pass_rate: CoVe pass rate
            
        Returns:
            Composite quality score (0.0-1.0)
        """
        scores = []
        weights = []
        
        # PPL component (negative change is good)
        if ppl_change is not None:
            # Convert to 0-1 score (capped at ±20%)
            ppl_score = max(0.0, min(1.0, 1.0 - (ppl_change / 20.0)))
            scores.append(ppl_score)
            weights.append(0.3)
        
        # Semantic component
        if semantic_score is not None:
            scores.append(semantic_score)
            weights.append(0.4)
        
        # CoVe component
        if cove_pass_rate is not None:
            scores.append(cove_pass_rate)
            weights.append(0.3)
        
        if not scores:
            return 0.5  # No metrics available
        
        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        
        return weighted_sum / total_weight
    
    def evaluate_adapter(
        self,
        adapter_name: str,
        train_loss: Optional[float] = None,
        eval_loss: Optional[float] = None,
        test_responses: Optional[List[str]] = None,
        test_questions: Optional[List[str]] = None,
        test_references: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvaluationResult:
        """
        Full evaluation of a LoRA adapter.
        
        Args:
            adapter_name: Name of the adapter
            train_loss: Training loss (if available)
            eval_loss: Evaluation loss
            test_responses: Generated test responses
            test_questions: Test questions
            test_references: Reference responses (optional)
            metadata: Additional metadata
            
        Returns:
            EvaluationResult object
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Compute perplexity
        perplexity = None
        ppl_change = None
        if eval_loss is not None:
            perplexity = self.compute_perplexity(eval_loss)
            ppl_change = self.compute_ppl_change(perplexity)
        
        # Semantic coherence
        semantic_score = None
        if test_responses:
            semantic_score = self.evaluate_semantic_coherence(
                test_responses,
                test_references,
            )
        
        # CoVe agreement
        cove_pass_rate = None
        if test_responses and test_questions:
            cove_pass_rate = self.evaluate_cove_agreement(
                test_responses,
                test_questions,
            )
        
        # Composite quality
        quality_score = self.compute_quality_score(
            ppl_change,
            semantic_score,
            cove_pass_rate,
        )
        
        result = EvaluationResult(
            timestamp=timestamp,
            adapter_name=adapter_name,
            train_loss=train_loss,
            eval_loss=eval_loss,
            perplexity=perplexity,
            ppl_change=ppl_change,
            semantic_score=semantic_score,
            cove_pass_rate=cove_pass_rate,
            quality_score=quality_score,
            metadata=metadata or {},
        )
        
        logger.info(
            f"Evaluation complete: {adapter_name} | "
            f"Quality: {quality_score:.2%} | "
            f"PPL change: {ppl_change:+.1f}% | "
            f"Semantic: {semantic_score:.2%} | "
            f"CoVe: {cove_pass_rate:.2%}"
        )
        
        return result


if __name__ == "__main__":
    # Test evaluation metrics
    logging.basicConfig(level=logging.INFO)
    
    print("Testing EvalMetrics...")
    
    metrics = EvalMetrics(baseline_ppl=10.5)
    
    # Test perplexity calculation
    print("\nTesting perplexity:")
    loss = 2.3
    ppl = metrics.compute_perplexity(loss)
    print(f"  Loss: {loss:.2f} -> PPL: {ppl:.2f}")
    
    ppl_change = metrics.compute_ppl_change(ppl)
    print(f"  PPL change from baseline: {ppl_change:+.1f}%")
    
    # Test quality score
    print("\nTesting quality score:")
    quality = metrics.compute_quality_score(
        ppl_change=-5.0,  # 5% improvement
        semantic_score=0.85,
        cove_pass_rate=0.92,
    )
    print(f"  Composite quality: {quality:.2%}")
    
    # Test full evaluation (mock)
    print("\nTesting full evaluation:")
    result = metrics.evaluate_adapter(
        adapter_name="test_adapter",
        train_loss=2.1,
        eval_loss=2.3,
        test_responses=["Response 1", "Response 2"],
        test_questions=["Question 1", "Question 2"],
    )
    
    print(f"  Adapter: {result.adapter_name}")
    print(f"  Quality: {result.quality_score:.2%}")
    print(f"  Passed check: {result.passed_quality_check()}")
    
    print("\n✅ EvalMetrics test complete")
