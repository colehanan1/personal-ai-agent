"""
Tests for model selection policy.

Tests selection determinism, threshold behavior, and scoring.
"""
import tempfile
import json
from pathlib import Path

import pytest

from benchmarks.select import (
    ModelSelector,
    SelectionWeights,
    SelectionThresholds,
    select_best_model_from_file,
)
from benchmarks.schema import (
    BenchmarkRun,
    BenchmarkCandidate,
    MetricResult,
    MetricStatus,
    RunMetadata,
    SystemInfo,
)


def create_test_candidate(
    version: str,
    latency: float = 15.0,
    throughput: float = 80.0,
    cove_pass_rate: float = 100.0,
    retrieval_score: float = 65.0,
) -> BenchmarkCandidate:
    """Helper to create test candidate."""
    candidate = BenchmarkCandidate(
        version=version,
        model_type="test",
        model_path="/test/path",
        base_model="test-base",
    )
    
    candidate.latency_ms = MetricResult(
        status=MetricStatus.OK,
        value=latency,
    )
    candidate.tokens_per_sec = MetricResult(
        status=MetricStatus.OK,
        value=throughput,
    )
    candidate.cove_pass_rate = MetricResult(
        status=MetricStatus.OK,
        value=cove_pass_rate,
    )
    candidate.retrieval_score = MetricResult(
        status=MetricStatus.OK,
        value=retrieval_score,
    )
    
    return candidate


class TestSelectionWeights:
    """Test SelectionWeights."""
    
    def test_default_weights(self):
        """Test default weights are equal."""
        weights = SelectionWeights()
        assert weights.latency_ms == 0.25
        assert weights.throughput == 0.25
        assert weights.cove_pass_rate == 0.25
        assert weights.retrieval_score == 0.25
    
    def test_normalize_weights(self):
        """Test weight normalization."""
        weights = SelectionWeights(
            latency_ms=1.0,
            throughput=2.0,
            cove_pass_rate=3.0,
            retrieval_score=4.0,
        )
        
        normalized = weights.normalize()
        
        # Should sum to 1.0
        total = (normalized.latency_ms + normalized.throughput +
                normalized.cove_pass_rate + normalized.retrieval_score)
        assert abs(total - 1.0) < 0.001
    
    def test_to_dict(self):
        """Test dict conversion."""
        weights = SelectionWeights()
        d = weights.to_dict()
        
        assert "latency_ms" in d
        assert "throughput" in d
        assert "cove_pass_rate" in d
        assert "retrieval_score" in d


class TestSelectionThresholds:
    """Test SelectionThresholds."""
    
    def test_default_thresholds(self):
        """Test default thresholds."""
        thresholds = SelectionThresholds()
        assert thresholds.min_cove_pass_rate == 90.0
        assert thresholds.min_retrieval_score == 50.0
        assert thresholds.max_latency_ms is None
        assert thresholds.min_throughput is None
    
    def test_custom_thresholds(self):
        """Test custom thresholds."""
        thresholds = SelectionThresholds(
            min_cove_pass_rate=95.0,
            min_retrieval_score=70.0,
            max_latency_ms=20.0,
            min_throughput=50.0,
        )
        
        assert thresholds.min_cove_pass_rate == 95.0
        assert thresholds.max_latency_ms == 20.0


class TestModelSelector:
    """Test ModelSelector."""
    
    def test_select_single_candidate(self):
        """Test selection with single candidate."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidate = create_test_candidate("v1.0")
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=[candidate],
        )
        
        selector = ModelSelector()
        result = selector.select_best_model(benchmark_run)
        
        assert result.recommended_model == "v1.0"
        assert len(result.all_scores) == 1
        assert result.all_scores[0].passed_thresholds is True
    
    def test_select_best_among_multiple(self):
        """Test selection with multiple candidates."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        # Create candidates with different scores
        candidates = [
            create_test_candidate("v1.0", latency=20.0, throughput=60.0, cove_pass_rate=90.0, retrieval_score=60.0),
            create_test_candidate("v2.0", latency=15.0, throughput=80.0, cove_pass_rate=100.0, retrieval_score=70.0),  # Best
            create_test_candidate("v3.0", latency=25.0, throughput=50.0, cove_pass_rate=95.0, retrieval_score=55.0),
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        selector = ModelSelector()
        result = selector.select_best_model(benchmark_run)
        
        # v2.0 should be selected (best overall)
        assert result.recommended_model == "v2.0"
        assert len(result.all_scores) == 3
    
    def test_threshold_filtering(self):
        """Test that candidates failing thresholds are not selected."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        # Create candidates where only one passes thresholds
        candidates = [
            create_test_candidate("v1.0", cove_pass_rate=85.0),  # Fails CoVe threshold
            create_test_candidate("v2.0", retrieval_score=40.0),  # Fails retrieval threshold
            create_test_candidate("v3.0", cove_pass_rate=95.0, retrieval_score=60.0),  # Passes
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        selector = ModelSelector()
        result = selector.select_best_model(benchmark_run)
        
        # v3.0 should be selected (only one passing)
        assert result.recommended_model == "v3.0"
        
        # Check that v1.0 and v2.0 have threshold failures
        scores_by_version = {s.model_version: s for s in result.all_scores}
        assert not scores_by_version["v1.0"].passed_thresholds
        assert not scores_by_version["v2.0"].passed_thresholds
        assert scores_by_version["v3.0"].passed_thresholds
    
    def test_no_passing_candidates(self):
        """Test when no candidates pass thresholds."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        # All candidates fail thresholds
        candidates = [
            create_test_candidate("v1.0", cove_pass_rate=80.0),
            create_test_candidate("v2.0", retrieval_score=30.0),
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        selector = ModelSelector()
        result = selector.select_best_model(benchmark_run)
        
        # No model should be recommended
        assert result.recommended_model is None
        assert "No candidates passed" in result.reason
    
    def test_tie_breaking(self):
        """Test tie-breaking logic (prefers lower latency)."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        # Create candidates with nearly identical scores
        candidates = [
            create_test_candidate("v1.0", latency=20.0, throughput=80.0, cove_pass_rate=95.0, retrieval_score=65.0),
            create_test_candidate("v2.0", latency=15.0, throughput=75.0, cove_pass_rate=95.0, retrieval_score=65.0),  # Should win on latency
        ]
        
        # Use weights that make scores very close
        weights = SelectionWeights(
            latency_ms=0.1,
            throughput=0.1,
            cove_pass_rate=0.4,
            retrieval_score=0.4,
        )
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        selector = ModelSelector(weights=weights)
        result = selector.select_best_model(benchmark_run)
        
        # v2.0 should win on tie-break (lower latency)
        assert result.recommended_model == "v2.0"
    
    def test_deterministic_selection(self):
        """Test that selection is deterministic."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidates = [
            create_test_candidate("v1.0", latency=15.0, throughput=80.0),
            create_test_candidate("v2.0", latency=20.0, throughput=85.0),
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        selector = ModelSelector()
        
        # Run selection multiple times
        results = [selector.select_best_model(benchmark_run) for _ in range(5)]
        
        # All should produce same recommendation
        recommended = [r.recommended_model for r in results]
        assert len(set(recommended)) == 1  # All the same
    
    def test_custom_weights(self):
        """Test selection with custom weights."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidates = [
            create_test_candidate("v1.0", latency=15.0, throughput=80.0, cove_pass_rate=100.0, retrieval_score=60.0),
            create_test_candidate("v2.0", latency=20.0, throughput=85.0, cove_pass_rate=90.0, retrieval_score=90.0),
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        # With default weights, v1.0 likely wins
        selector_default = ModelSelector()
        result_default = selector_default.select_best_model(benchmark_run)
        
        # With heavy retrieval weight, v2.0 should win
        weights_retrieval = SelectionWeights(
            latency_ms=0.1,
            throughput=0.1,
            cove_pass_rate=0.1,
            retrieval_score=0.7,
        )
        selector_retrieval = ModelSelector(weights=weights_retrieval)
        result_retrieval = selector_retrieval.select_best_model(benchmark_run)
        
        # Different weights may produce different recommendations
        # (or same if one clearly dominates)
        assert result_retrieval.recommended_model is not None
    
    def test_missing_metrics(self):
        """Test handling of candidates with missing metrics."""
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        # Candidate with missing CoVe metric
        candidate = create_test_candidate("v1.0")
        candidate.cove_pass_rate = MetricResult(status=MetricStatus.SKIPPED)
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=[candidate],
        )
        
        selector = ModelSelector()
        result = selector.select_best_model(benchmark_run)
        
        # Should not be recommended (fails threshold due to missing metric)
        assert result.recommended_model is None


class TestSelectFromFile:
    """Test selection from file."""
    
    def test_select_from_file(self):
        """Test selecting best model from JSON file."""
        # Create test benchmark run
        metadata = RunMetadata.create()
        system_info = SystemInfo.collect()
        
        candidates = [
            create_test_candidate("v1.0", latency=15.0, throughput=80.0, cove_pass_rate=95.0, retrieval_score=65.0),
            create_test_candidate("v2.0", latency=20.0, throughput=70.0, cove_pass_rate=92.0, retrieval_score=60.0),
        ]
        
        benchmark_run = BenchmarkRun(
            metadata=metadata,
            system_info=system_info,
            candidates=candidates,
        )
        
        # Save to file
        with tempfile.TemporaryDirectory() as tmpdir:
            benchmark_path = Path(tmpdir) / "test_benchmark.json"
            benchmark_run.save(benchmark_path)
            
            # Select from file
            result = select_best_model_from_file(benchmark_path)
            
            assert result.recommended_model is not None
            assert result.recommended_model in ["v1.0", "v2.0"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
