"""
Tests for benchmark measurement and statistics.

Tests timing functions, statistics computation, and aggregation
with mocked responses (hermetic).
"""
import time
from unittest.mock import Mock

import pytest

from benchmarks.backends.base import InferenceResult
from benchmarks.measure import (
    compute_stats,
    run_repeated_measurement,
    run_prompt_benchmark,
    aggregate_measurements,
    MeasurementStats,
    BenchmarkMeasurement,
)


class TestComputeStats:
    """Test statistics computation."""
    
    def test_basic_stats(self):
        """Test basic statistics calculation."""
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_stats(values)
        
        assert stats is not None
        assert stats.mean == 30.0
        assert stats.median == 30.0
        assert stats.min_val == 10.0
        assert stats.max_val == 50.0
        assert stats.count == 5
    
    def test_empty_list(self):
        """Test with empty list."""
        stats = compute_stats([])
        assert stats is None
    
    def test_single_value(self):
        """Test with single value."""
        stats = compute_stats([42.0])
        assert stats is not None
        assert stats.mean == 42.0
        assert stats.median == 42.0
        assert stats.std_dev == 0.0
    
    def test_filters_none(self):
        """Test that None values are filtered."""
        values = [10.0, None, 20.0, None, 30.0]
        stats = compute_stats(values)
        
        assert stats is not None
        assert stats.count == 3
        assert stats.mean == 20.0
    
    def test_filters_inf(self):
        """Test that infinite values are filtered."""
        values = [10.0, float('inf'), 20.0, float('-inf'), 30.0]
        stats = compute_stats(values)
        
        assert stats is not None
        assert stats.count == 3
        assert stats.mean == 20.0
    
    def test_percentiles(self):
        """Test percentile calculation."""
        values = list(range(1, 101))  # 1 to 100
        stats = compute_stats([float(v) for v in values])
        
        assert stats is not None
        assert 94 <= stats.p95 <= 96
        assert 98 <= stats.p99 <= 100


class TestMeasurementStats:
    """Test MeasurementStats dataclass."""
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = MeasurementStats(
            mean=50.5,
            median=49.0,
            std_dev=5.2,
            min_val=40.0,
            max_val=60.0,
            p95=58.0,
            p99=59.5,
            count=10,
        )
        
        d = stats.to_dict()
        assert d["mean"] == 50.5
        assert d["median"] == 49.0
        assert d["count"] == 10


class TestBenchmarkMeasurement:
    """Test BenchmarkMeasurement dataclass."""
    
    def test_basic_measurement(self):
        """Test basic measurement structure."""
        measurement = BenchmarkMeasurement(
            success_count=5,
            error_count=0,
        )
        
        assert measurement.success_count == 5
        assert measurement.error_count == 0
        assert measurement.errors == []
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = MeasurementStats(
            mean=100.0,
            median=100.0,
            std_dev=10.0,
            min_val=80.0,
            max_val=120.0,
            p95=115.0,
            p99=118.0,
            count=10,
        )
        
        measurement = BenchmarkMeasurement(
            first_token_latency_ms=stats,
            success_count=10,
            error_count=0,
        )
        
        d = measurement.to_dict()
        assert d["success_count"] == 10
        assert "first_token_latency_ms" in d
        assert d["first_token_latency_ms"]["mean"] == 100.0


class TestRunRepeatedMeasurement:
    """Test repeated measurement execution."""
    
    def test_successful_measurements(self):
        """Test successful repeated measurements."""
        call_count = [0]
        
        def mock_measurement():
            call_count[0] += 1
            return InferenceResult(
                prompt="test",
                response="response",
                first_token_latency_ms=100.0 + call_count[0],
                total_latency_ms=500.0 + call_count[0] * 10,
                tokens_per_sec=50.0,
            )
        
        result = run_repeated_measurement(
            measurement_fn=mock_measurement,
            num_iterations=5,
            warmup_iterations=2,
        )
        
        # Total calls = warmup + iterations
        assert call_count[0] == 7
        
        # Check results
        assert result.success_count == 5
        assert result.error_count == 0
        assert result.first_token_latency_ms is not None
        assert result.total_latency_ms is not None
        assert result.tokens_per_sec is not None
    
    def test_measurements_with_errors(self):
        """Test measurements with some errors."""
        call_count = [0]
        
        def mock_measurement():
            call_count[0] += 1
            # Every other call fails
            if call_count[0] % 2 == 0:
                return InferenceResult(
                    prompt="test",
                    response="",
                    error="Mock error",
                )
            else:
                return InferenceResult(
                    prompt="test",
                    response="response",
                    total_latency_ms=100.0,
                )
        
        result = run_repeated_measurement(
            measurement_fn=mock_measurement,
            num_iterations=4,
            warmup_iterations=0,
        )
        
        assert result.success_count == 2
        assert result.error_count == 2
        assert "Mock error" in result.errors
    
    def test_warmup_discarded(self):
        """Test that warmup iterations are discarded."""
        call_count = [0]
        values = []
        
        def mock_measurement():
            call_count[0] += 1
            value = float(call_count[0])
            if call_count[0] > 2:  # After warmup
                values.append(value)
            return InferenceResult(
                prompt="test",
                response="response",
                total_latency_ms=value,
            )
        
        result = run_repeated_measurement(
            measurement_fn=mock_measurement,
            num_iterations=3,
            warmup_iterations=2,
        )
        
        # Only non-warmup values should be in stats
        assert result.total_latency_ms is not None
        assert result.total_latency_ms.count == 3
        # Mean should be of values [3, 4, 5]
        assert result.total_latency_ms.mean == 4.0


class TestRunPromptBenchmark:
    """Test prompt benchmarking."""
    
    def test_prompt_benchmark(self):
        """Test benchmarking a single prompt."""
        mock_backend = Mock()
        mock_backend.run_inference.return_value = InferenceResult(
            prompt="test prompt",
            response="test response",
            first_token_latency_ms=50.0,
            total_latency_ms=200.0,
            tokens_per_sec=100.0,
        )
        
        result = run_prompt_benchmark(
            backend=mock_backend,
            prompt="test prompt",
            num_iterations=3,
            warmup_iterations=1,
            max_tokens=100,
            temperature=0.7,
        )
        
        # Should call backend 4 times (1 warmup + 3 iterations)
        assert mock_backend.run_inference.call_count == 4
        
        # Check results
        assert result.success_count == 3
        assert result.first_token_latency_ms is not None
        assert result.first_token_latency_ms.mean == 50.0


class TestAggregateMeasurements:
    """Test measurement aggregation."""
    
    def test_aggregate_multiple_measurements(self):
        """Test aggregating multiple measurements."""
        measurements = []
        
        for i in range(3):
            stats = MeasurementStats(
                mean=100.0 + i * 10,
                median=100.0 + i * 10,
                std_dev=5.0,
                min_val=90.0 + i * 10,
                max_val=110.0 + i * 10,
                p95=108.0,
                p99=109.0,
                count=5,
            )
            
            measurement = BenchmarkMeasurement(
                first_token_latency_ms=stats,
                total_latency_ms=stats,
                tokens_per_sec=stats,
                success_count=5,
                error_count=0,
            )
            measurements.append(measurement)
        
        aggregated = aggregate_measurements(measurements)
        
        # Should aggregate across all measurements
        assert aggregated.success_count == 15
        assert aggregated.error_count == 0
        
        # Should compute stats from means
        assert aggregated.first_token_latency_ms is not None
        # Means are [100, 110, 120], so aggregated mean is 110
        assert aggregated.first_token_latency_ms.mean == 110.0
    
    def test_aggregate_with_errors(self):
        """Test aggregation includes all errors."""
        measurements = [
            BenchmarkMeasurement(
                success_count=3,
                error_count=1,
                errors=["Error A"],
            ),
            BenchmarkMeasurement(
                success_count=4,
                error_count=2,
                errors=["Error B", "Error A"],
            ),
        ]
        
        aggregated = aggregate_measurements(measurements)
        
        assert aggregated.success_count == 7
        assert aggregated.error_count == 3
        # Should deduplicate errors
        assert len(aggregated.errors) == 2
        assert "Error A" in aggregated.errors
        assert "Error B" in aggregated.errors
    
    def test_aggregate_empty_list(self):
        """Test aggregating empty list."""
        aggregated = aggregate_measurements([])
        
        assert aggregated.success_count == 0
        assert aggregated.error_count == 0
        assert aggregated.first_token_latency_ms is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
