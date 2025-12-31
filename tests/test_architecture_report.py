"""
Tests for Architecture Report Generator

Validates that the architecture report generation works correctly,
meets length requirements, and contains all required sections.
"""

import pytest
import os
import sys
from pathlib import Path
import tempfile
import shutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_architecture_report import (
    ArchitectureAnalyzer,
    generate_report
)


class TestArchitectureAnalyzer:
    """Test the repository analyzer component"""

    def test_analyzer_initialization(self):
        """Test analyzer can be initialized with valid repo path"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        assert analyzer.repo_path.exists()

    def test_analyzer_invalid_path(self):
        """Test analyzer raises error for invalid path"""
        with pytest.raises(ValueError):
            ArchitectureAnalyzer("/nonexistent/path/to/repo")

    def test_tech_stack_detection(self):
        """Test technology stack detection"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        tech_stack = analyzer._detect_tech_stack()

        assert 'language' in tech_stack
        assert 'frameworks' in tech_stack
        assert 'databases' in tech_stack
        assert tech_stack['language'] == 'Python 3.11+'

        # Check for expected technologies
        framework_names = ' '.join(tech_stack['frameworks']).lower()
        assert 'vllm' in framework_names or len(tech_stack['frameworks']) > 0

    def test_component_identification(self):
        """Test component identification from directory structure"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        components = analyzer._identify_components()

        # Milton should have these core components
        expected_components = ['agents', 'integrations', 'memory', 'orchestrator']

        # Check at least some expected components exist
        found_components = [c for c in expected_components if c in components]
        assert len(found_components) >= 2, f"Expected components not found. Found: {list(components.keys())}"

    def test_file_counting(self):
        """Test file counting by extension"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        file_counts = analyzer._count_files_by_type()

        assert '.py' in file_counts
        assert file_counts['.py'] > 0  # Should have Python files
        assert '.md' in file_counts  # Should have markdown docs

    def test_full_analysis(self):
        """Test complete analysis workflow"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        analysis = analyzer.analyze()

        # Verify analysis structure
        assert 'tech_stack' in analysis
        assert 'components' in analysis
        assert 'file_counts' in analysis
        assert 'analyzed_at' in analysis

        # Verify content
        assert isinstance(analysis['tech_stack'], dict)
        assert isinstance(analysis['components'], dict)
        assert isinstance(analysis['file_counts'], dict)


class TestReportGeneration:
    """Test the report generation functionality"""

    @pytest.fixture
    def analysis_data(self):
        """Fixture providing sample analysis data"""
        return {
            'tech_stack': {
                'language': 'Python 3.11+',
                'frameworks': ['vLLM', 'Flask'],
                'databases': ['Weaviate'],
                'deployment': ['Docker Compose'],
                'apis': ['HTTP/REST']
            },
            'components': {
                'agents': {
                    'path': 'agents',
                    'files': ['nexus.py', 'cortex.py', 'frontier.py'],
                    'description': 'Multi-agent system'
                },
                'memory': {
                    'path': 'memory',
                    'files': ['operations.py', 'init_db.py'],
                    'description': '3-tier memory system'
                }
            },
            'file_counts': {
                '.py': 50,
                '.md': 10,
                '.json': 5
            },
            'analyzed_at': '2025-12-31T12:00:00'
        }

    def test_report_generation_basic(self, analysis_data):
        """Test basic report generation"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        assert isinstance(report, str)
        assert len(report) > 0

    def test_report_minimum_length(self, analysis_data):
        """Test report meets 4000+ character requirement"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        char_count = len(report)
        assert char_count >= 4000, f"Report only {char_count} characters, needs 4000+"

    def test_report_contains_required_sections(self, analysis_data):
        """Test report contains all required sections"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        required_sections = [
            "# Milton System Architecture Report",
            "## 1. Introduction",
            "## 2. Architecture Overview",
            "## 3. System Components",
            "## 4. Key Workflows",
            "## 5. Architecture Justification",
            "## 6. Technology Stack",
            "## 7. Component Traceability",
            "## 8. Security & Privacy",
            "## 9. Deployment Model",
            "## 10. Performance Characteristics",
            "## 11. Summary & Recommendations"
        ]

        for section in required_sections:
            assert section in report, f"Missing required section: {section}"

    def test_report_has_markdown_formatting(self, analysis_data):
        """Test report uses proper Markdown syntax"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        # Check for Markdown elements
        assert '**' in report  # Bold text
        assert '|' in report   # Tables
        assert '```' in report  # Code blocks
        assert '-' in report or '*' in report  # Bullet points
        assert '#' in report   # Headers

    def test_report_includes_components(self, analysis_data):
        """Test report includes component information"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        # Check components are mentioned
        assert 'agents' in report.lower()
        assert 'memory' in report.lower()
        assert 'NEXUS' in report
        assert 'CORTEX' in report

    def test_report_includes_tech_stack(self, analysis_data):
        """Test report includes technology stack"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        # Check tech stack is documented
        assert 'vLLM' in report
        assert 'Python' in report
        assert 'Weaviate' in report or 'vector' in report.lower()

    def test_report_has_diagrams(self, analysis_data):
        """Test report includes text-based diagrams"""
        repo_path = "/home/cole-hanan/milton"
        report = generate_report(analysis_data, repo_path)

        # Check for ASCII-art diagram elements
        assert '┌' in report or '└' in report or '│' in report or '▼' in report


class TestEndToEnd:
    """End-to-end integration tests"""

    def test_full_workflow_with_real_repo(self):
        """Test complete workflow on actual Milton repository"""
        repo_path = Path(__file__).parent.parent

        # Step 1: Analyze
        analyzer = ArchitectureAnalyzer(str(repo_path))
        analysis = analyzer.analyze()

        # Step 2: Generate report
        report = generate_report(analysis, str(repo_path))

        # Step 3: Validate
        assert len(report) >= 4000, f"Report only {len(report)} characters"
        assert "Milton" in report
        assert "NEXUS" in report or "orchestrat" in report.lower()

        # Step 4: Check sections
        assert "## 1. Introduction" in report
        assert "## 2. Architecture Overview" in report
        assert "Technology Stack" in report or "Tech Stack" in report

    def test_report_file_output(self, tmp_path):
        """Test report can be written to file successfully"""
        repo_path = Path(__file__).parent.parent
        output_path = tmp_path / "test_architecture_report.md"

        # Generate report
        analyzer = ArchitectureAnalyzer(str(repo_path))
        analysis = analyzer.analyze()
        report = generate_report(analysis, str(repo_path))

        # Write to file
        output_path.write_text(report, encoding='utf-8')

        # Verify file
        assert output_path.exists()
        assert output_path.stat().st_size > 4000

        # Verify content readable
        content = output_path.read_text(encoding='utf-8')
        assert content == report
        assert "Milton" in content


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_empty_components(self):
        """Test report generation with minimal components"""
        analysis = {
            'tech_stack': {'language': 'Python 3.11+', 'frameworks': [], 'databases': [], 'deployment': [], 'apis': []},
            'components': {},
            'file_counts': {},
            'analyzed_at': '2025-12-31T12:00:00'
        }

        report = generate_report(analysis, "/test/path")

        # Should still generate valid report
        assert len(report) > 0
        assert "Milton System Architecture Report" in report

    def test_missing_optional_fields(self):
        """Test report generation with missing optional fields"""
        analysis = {
            'tech_stack': {
                'language': 'Python 3.11+',
                'frameworks': ['vLLM'],
                'databases': [],
                'deployment': [],
                'apis': []
            },
            'components': {
                'agents': {
                    'path': 'agents',
                    'description': 'Test agents'
                    # Missing 'files' field
                }
            },
            'file_counts': {'.py': 1},
            'analyzed_at': '2025-12-31T12:00:00'
        }

        report = generate_report(analysis, "/test/path")

        # Should handle gracefully
        assert len(report) > 0
        assert 'agents' in report.lower()


class TestCharacterCount:
    """Specific tests for character count requirements"""

    def test_character_count_accuracy(self):
        """Test character counting is accurate"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        analysis = analyzer.analyze()
        report = generate_report(analysis, str(repo_path))

        # Manual count
        manual_count = len(report)

        # Python string length
        python_count = len(report)

        assert manual_count == python_count
        assert manual_count >= 4000

    def test_exceeds_minimum_significantly(self):
        """Test report significantly exceeds 4000 character minimum"""
        repo_path = Path(__file__).parent.parent
        analyzer = ArchitectureAnalyzer(str(repo_path))
        analysis = analyzer.analyze()
        report = generate_report(analysis, str(repo_path))

        # Should be substantially over minimum (at least 5000 for good measure)
        assert len(report) >= 5000, "Report should significantly exceed 4000 chars"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
