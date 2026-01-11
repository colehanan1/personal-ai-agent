"""
Unit tests for llama.cpp tool discovery in ModelCompression.

Tests the _find_quantize_binary() method to ensure it can locate
the quantize binary in various llama.cpp directory layouts (CMake, Make, etc.).
"""
import os
import tempfile
from pathlib import Path
import pytest

from training.model_compression import ModelCompression


class TestToolDiscovery:
    """Test llama.cpp tool discovery logic."""
    
    def test_find_quantize_in_cmake_bin_dir(self):
        """Test finding quantize in build/bin/ (modern CMake layout)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create CMake layout: build/bin/llama-quantize
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            quantize_path = bin_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            # Create compression instance
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            
            # Should find the binary
            found = mc._find_quantize_binary()
            assert found is not None
            assert found.name == "llama-quantize"
            assert "build/bin" in str(found)
    
    def test_find_quantize_alternative_name(self):
        """Test finding 'quantize' (without llama- prefix)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create CMake layout: build/bin/quantize (alternative name)
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            quantize_path = bin_dir / "quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            assert found is not None
            assert found.name == "quantize"
    
    def test_find_quantize_in_build_root(self):
        """Test finding quantize in build/ (alternative CMake layout)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create layout: build/llama-quantize
            build_dir = llama_dir / "build"
            build_dir.mkdir()
            quantize_path = build_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            assert found is not None
            assert "build" in str(found)
    
    def test_find_quantize_legacy_make(self):
        """Test finding quantize in root dir (legacy Make build)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create legacy layout: llama-quantize in root
            quantize_path = llama_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            assert found is not None
            assert found.parent == llama_dir
    
    def test_find_quantize_priority_order(self):
        """Test that CMake locations are preferred over legacy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create both CMake and legacy binaries
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            cmake_binary = bin_dir / "llama-quantize"
            cmake_binary.touch()
            cmake_binary.chmod(0o755)
            
            legacy_binary = llama_dir / "llama-quantize"
            legacy_binary.touch()
            legacy_binary.chmod(0o755)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            # Should prefer CMake location
            assert found == cmake_binary
            assert "build/bin" in str(found)
    
    def test_find_quantize_not_executable(self):
        """Test that non-executable files are not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create binary without execute permission
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            quantize_path = bin_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o644)  # No execute permission
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            # Should not find non-executable file
            assert found is None
    
    def test_find_quantize_missing(self):
        """Test behavior when no quantize binary exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            found = mc._find_quantize_binary()
            
            assert found is None
    
    def test_find_quantize_no_llama_cpp_dir(self):
        """Test behavior when llama_cpp_dir is not set."""
        mc = ModelCompression()
        found = mc._find_quantize_binary()
        
        assert found is None
    
    def test_check_llama_cpp_with_valid_tools(self):
        """Test _check_llama_cpp() with all required tools present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Create quantize binary
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            quantize_path = bin_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            # Create convert script
            convert_script = llama_dir / "convert_hf_to_gguf.py"
            convert_script.touch()
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            
            assert mc._check_llama_cpp() is True
    
    def test_check_llama_cpp_missing_quantize(self):
        """Test _check_llama_cpp() with missing quantize binary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Only create convert script
            convert_script = llama_dir / "convert_hf_to_gguf.py"
            convert_script.touch()
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            
            assert mc._check_llama_cpp() is False
    
    def test_check_llama_cpp_missing_convert(self):
        """Test _check_llama_cpp() with missing convert script."""
        with tempfile.TemporaryDirectory() as tmpdir:
            llama_dir = Path(tmpdir)
            
            # Only create quantize binary
            bin_dir = llama_dir / "build" / "bin"
            bin_dir.mkdir(parents=True)
            quantize_path = bin_dir / "llama-quantize"
            quantize_path.touch()
            quantize_path.chmod(0o755)
            
            mc = ModelCompression(llama_cpp_dir=llama_dir)
            
            assert mc._check_llama_cpp() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
