"""
Model selection policy for benchmark-driven model recommendation.

Implements weighted scoring with configurable thresholds and tie-breakers
to select the best model from benchmark results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from benchmarks.schema import BenchmarkRun, MetricStatus

logger = logging.getLogger(__name__)


@dataclass
class SelectionWeights:
    """Weights for different metrics in model selection."""
    latency_ms: float = 0.25
    throughput: float = 0.25
    cove_pass_rate: float = 0.25
    retrieval_score: float = 0.25
    
    def normalize(self) -> SelectionWeights:
        """Normalize weights to sum to 1.0."""
        total = self.latency_ms + self.throughput + self.cove_pass_rate + self.retrieval_score
        if total == 0:
            return SelectionWeights()
        return SelectionWeights(
            latency_ms=self.latency_ms / total,
            throughput=self.throughput / total,
            cove_pass_rate=self.cove_pass_rate / total,
            retrieval_score=self.retrieval_score / total,
        )
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary."""
        return {
            "latency_ms": self.latency_ms,
            "throughput": self.throughput,
            "cove_pass_rate": self.cove_pass_rate,
            "retrieval_score": self.retrieval_score,
        }


@dataclass
class SelectionThresholds:
    """Minimum thresholds for model selection."""
    min_cove_pass_rate: float = 90.0  # Minimum 90% CoVe pass rate
    min_retrieval_score: float = 50.0  # Minimum 50% retrieval score
    max_latency_ms: Optional[float] = None  # Optional max latency
    min_throughput: Optional[float] = None  # Optional min throughput
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "min_cove_pass_rate": self.min_cove_pass_rate,
            "min_retrieval_score": self.min_retrieval_score,
            "max_latency_ms": self.max_latency_ms,
            "min_throughput": self.min_throughput,
        }


@dataclass
class ModelScore:
    """Score for a model candidate."""
    model_version: str
    total_score: float
    component_scores: Dict[str, float]
    normalized_metrics: Dict[str, Optional[float]]
    passed_thresholds: bool
    threshold_failures: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model_version": self.model_version,
            "total_score": round(self.total_score, 4),
            "component_scores": {k: round(v, 4) for k, v in self.component_scores.items()},
            "normalized_metrics": {k: round(v, 4) if v is not None else None 
                                  for k, v in self.normalized_metrics.items()},
            "passed_thresholds": self.passed_thresholds,
            "threshold_failures": self.threshold_failures,
        }


@dataclass
class SelectionResult:
    """Result of model selection process."""
    recommended_model: Optional[str]
    all_scores: List[ModelScore]
    selection_metadata: Dict[str, Any]
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "recommended_model": self.recommended_model,
            "all_scores": [score.to_dict() for score in self.all_scores],
            "selection_metadata": self.selection_metadata,
            "reason": self.reason,
        }


class ModelSelector:
    """
    Model selector based on weighted scoring.
    
    Implements:
    - Weighted scoring across multiple metrics
    - Minimum threshold enforcement
    - Tie-breaking rules
    - Normalization of metrics
    """
    
    def __init__(
        self,
        weights: Optional[SelectionWeights] = None,
        thresholds: Optional[SelectionThresholds] = None,
    ):
        """
        Initialize model selector.
        
        Args:
            weights: Metric weights (will be normalized)
            thresholds: Minimum thresholds for selection
        """
        self.weights = (weights or SelectionWeights()).normalize()
        self.thresholds = thresholds or SelectionThresholds()
    
    def select_best_model(
        self,
        benchmark_run: BenchmarkRun,
    ) -> SelectionResult:
        """
        Select the best model from benchmark results.
        
        Args:
            benchmark_run: Benchmark run with candidate results
        
        Returns:
            SelectionResult with recommendation
        """
        if not benchmark_run.candidates:
            return SelectionResult(
                recommended_model=None,
                all_scores=[],
                selection_metadata={},
                reason="No candidates in benchmark run",
            )
        
        # Extract metrics from all candidates
        all_metrics = self._extract_all_metrics(benchmark_run.candidates)
        
        # Normalize metrics
        normalization_params = self._compute_normalization_params(all_metrics)
        
        # Score each candidate
        scores = []
        for candidate in benchmark_run.candidates:
            score = self._score_candidate(candidate, normalization_params)
            scores.append(score)
        
        # Sort by total score (descending)
        scores.sort(key=lambda s: s.total_score, reverse=True)
        
        # Filter by thresholds
        passing_scores = [s for s in scores if s.passed_thresholds]
        
        if not passing_scores:
            return SelectionResult(
                recommended_model=None,
                all_scores=scores,
                selection_metadata={
                    "weights": self.weights.to_dict(),
                    "thresholds": self.thresholds.to_dict(),
                    "normalization_params": normalization_params,
                },
                reason="No candidates passed minimum thresholds",
            )
        
        # Select best (already sorted)
        best = passing_scores[0]
        
        # Check for ties (within 0.01 score)
        ties = [s for s in passing_scores if abs(s.total_score - best.total_score) < 0.01]
        
        if len(ties) > 1:
            # Tie-breaker: prefer lower latency, then higher throughput
            ties.sort(key=lambda s: (
                s.normalized_metrics.get("latency_ms", float('inf')),
                -s.normalized_metrics.get("throughput", 0),
            ))
            best = ties[0]
            reason = f"Selected {best.model_version} (score: {best.total_score:.4f}, tie-broken by latency)"
        else:
            reason = f"Selected {best.model_version} (score: {best.total_score:.4f})"
        
        return SelectionResult(
            recommended_model=best.model_version,
            all_scores=scores,
            selection_metadata={
                "weights": self.weights.to_dict(),
                "thresholds": self.thresholds.to_dict(),
                "normalization_params": normalization_params,
            },
            reason=reason,
        )
    
    def _extract_all_metrics(
        self,
        candidates: List,
    ) -> Dict[str, List[float]]:
        """
        Extract all valid metrics from candidates.
        
        Args:
            candidates: List of BenchmarkCandidate objects
        
        Returns:
            Dictionary mapping metric names to lists of values
        """
        all_metrics = {
            "latency_ms": [],
            "throughput": [],
            "cove_pass_rate": [],
            "retrieval_score": [],
        }
        
        for candidate in candidates:
            # Latency (first token)
            if candidate.latency_ms.status == MetricStatus.OK and candidate.latency_ms.value is not None:
                all_metrics["latency_ms"].append(candidate.latency_ms.value)
            
            # Throughput
            if candidate.tokens_per_sec.status == MetricStatus.OK and candidate.tokens_per_sec.value is not None:
                all_metrics["throughput"].append(candidate.tokens_per_sec.value)
            
            # CoVe pass rate
            if candidate.cove_pass_rate.status == MetricStatus.OK and candidate.cove_pass_rate.value is not None:
                all_metrics["cove_pass_rate"].append(candidate.cove_pass_rate.value)
            
            # Retrieval score
            if candidate.retrieval_score.status == MetricStatus.OK and candidate.retrieval_score.value is not None:
                all_metrics["retrieval_score"].append(candidate.retrieval_score.value)
        
        return all_metrics
    
    def _compute_normalization_params(
        self,
        all_metrics: Dict[str, List[float]],
    ) -> Dict[str, Tuple[float, float]]:
        """
        Compute min/max for normalization.
        
        Args:
            all_metrics: Dictionary of metric values
        
        Returns:
            Dictionary mapping metric names to (min, max) tuples
        """
        params = {}
        
        for metric_name, values in all_metrics.items():
            if not values:
                params[metric_name] = (0.0, 1.0)  # Default range
            else:
                min_val = min(values)
                max_val = max(values)
                
                # Avoid division by zero
                if min_val == max_val:
                    params[metric_name] = (min_val, min_val + 1.0)
                else:
                    params[metric_name] = (min_val, max_val)
        
        return params
    
    def _score_candidate(
        self,
        candidate,
        normalization_params: Dict[str, Tuple[float, float]],
    ) -> ModelScore:
        """
        Score a single candidate.
        
        Args:
            candidate: BenchmarkCandidate object
            normalization_params: Normalization parameters
        
        Returns:
            ModelScore
        """
        component_scores = {}
        normalized_metrics = {}
        threshold_failures = []
        
        # Latency (lower is better, so invert normalization)
        latency_value = None
        if candidate.latency_ms.status == MetricStatus.OK and candidate.latency_ms.value is not None:
            latency_value = candidate.latency_ms.value
            min_lat, max_lat = normalization_params["latency_ms"]
            if max_lat > min_lat:
                # Invert: 0 = worst (max), 1 = best (min)
                normalized = 1.0 - ((latency_value - min_lat) / (max_lat - min_lat))
            else:
                normalized = 1.0
            normalized_metrics["latency_ms"] = latency_value
            component_scores["latency_ms"] = normalized * self.weights.latency_ms
            
            # Check threshold
            if self.thresholds.max_latency_ms is not None and latency_value > self.thresholds.max_latency_ms:
                threshold_failures.append(f"Latency {latency_value:.2f}ms exceeds max {self.thresholds.max_latency_ms:.2f}ms")
        else:
            normalized_metrics["latency_ms"] = None
            component_scores["latency_ms"] = 0.0
            if self.thresholds.max_latency_ms is not None:
                threshold_failures.append("Latency not available")
        
        # Throughput (higher is better)
        throughput_value = None
        if candidate.tokens_per_sec.status == MetricStatus.OK and candidate.tokens_per_sec.value is not None:
            throughput_value = candidate.tokens_per_sec.value
            min_tps, max_tps = normalization_params["throughput"]
            if max_tps > min_tps:
                normalized = (throughput_value - min_tps) / (max_tps - min_tps)
            else:
                normalized = 1.0
            normalized_metrics["throughput"] = throughput_value
            component_scores["throughput"] = normalized * self.weights.throughput
            
            # Check threshold
            if self.thresholds.min_throughput is not None and throughput_value < self.thresholds.min_throughput:
                threshold_failures.append(f"Throughput {throughput_value:.2f} below min {self.thresholds.min_throughput:.2f}")
        else:
            normalized_metrics["throughput"] = None
            component_scores["throughput"] = 0.0
            if self.thresholds.min_throughput is not None:
                threshold_failures.append("Throughput not available")
        
        # CoVe pass rate (higher is better, already 0-100)
        cove_value = None
        if candidate.cove_pass_rate.status == MetricStatus.OK and candidate.cove_pass_rate.value is not None:
            cove_value = candidate.cove_pass_rate.value
            normalized = cove_value / 100.0  # Normalize to 0-1
            normalized_metrics["cove_pass_rate"] = cove_value
            component_scores["cove_pass_rate"] = normalized * self.weights.cove_pass_rate
            
            # Check threshold
            if cove_value < self.thresholds.min_cove_pass_rate:
                threshold_failures.append(f"CoVe pass rate {cove_value:.1f}% below min {self.thresholds.min_cove_pass_rate:.1f}%")
        else:
            normalized_metrics["cove_pass_rate"] = None
            component_scores["cove_pass_rate"] = 0.0
            threshold_failures.append("CoVe pass rate not available")
        
        # Retrieval score (higher is better, already 0-100)
        retrieval_value = None
        if candidate.retrieval_score.status == MetricStatus.OK and candidate.retrieval_score.value is not None:
            retrieval_value = candidate.retrieval_score.value
            normalized = retrieval_value / 100.0  # Normalize to 0-1
            normalized_metrics["retrieval_score"] = retrieval_value
            component_scores["retrieval_score"] = normalized * self.weights.retrieval_score
            
            # Check threshold
            if retrieval_value < self.thresholds.min_retrieval_score:
                threshold_failures.append(f"Retrieval score {retrieval_value:.1f}% below min {self.thresholds.min_retrieval_score:.1f}%")
        else:
            normalized_metrics["retrieval_score"] = None
            component_scores["retrieval_score"] = 0.0
            threshold_failures.append("Retrieval score not available")
        
        # Total score
        total_score = sum(component_scores.values())
        
        return ModelScore(
            model_version=candidate.version,
            total_score=total_score,
            component_scores=component_scores,
            normalized_metrics=normalized_metrics,
            passed_thresholds=len(threshold_failures) == 0,
            threshold_failures=threshold_failures,
        )


def select_best_model_from_file(
    benchmark_path: Path,
    weights: Optional[SelectionWeights] = None,
    thresholds: Optional[SelectionThresholds] = None,
) -> SelectionResult:
    """
    Select best model from a benchmark results file.
    
    Args:
        benchmark_path: Path to benchmark JSON file
        weights: Optional custom weights
        thresholds: Optional custom thresholds
    
    Returns:
        SelectionResult
    """
    benchmark_run = BenchmarkRun.load(benchmark_path)
    selector = ModelSelector(weights=weights, thresholds=thresholds)
    return selector.select_best_model(benchmark_run)
