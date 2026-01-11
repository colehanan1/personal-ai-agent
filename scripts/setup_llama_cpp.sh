#!/usr/bin/env bash
# Setup llama.cpp with CMake build system
# This script clones llama.cpp (if needed) and builds it with CMake
# to produce the quantize binary required for model compression.

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
REPO_URL="https://github.com/ggerganov/llama.cpp"
BUILD_TYPE="${BUILD_TYPE:-Release}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc 2>/dev/null || echo 4)}"

echo "=================================================="
echo "llama.cpp Setup Script"
echo "=================================================="
echo "Target directory: $LLAMA_CPP_DIR"
echo "Build type: $BUILD_TYPE"
echo "Build jobs: $BUILD_JOBS"
echo

# Check prerequisites
if ! command -v cmake &> /dev/null; then
    echo "ERROR: cmake not found. Please install cmake first:"
    echo "  sudo apt-get install cmake"
    echo "  or"
    echo "  conda install cmake"
    exit 1
fi

if ! command -v g++ &> /dev/null && ! command -v clang++ &> /dev/null; then
    echo "ERROR: No C++ compiler found. Please install g++ or clang++:"
    echo "  sudo apt-get install build-essential"
    exit 1
fi

# Clone if needed
if [ ! -d "$LLAMA_CPP_DIR" ]; then
    echo "Cloning llama.cpp repository..."
    git clone "$REPO_URL" "$LLAMA_CPP_DIR"
    echo "✓ Repository cloned"
else
    echo "✓ Repository exists at $LLAMA_CPP_DIR"
    
    # Check if it's actually a llama.cpp repo
    if [ ! -f "$LLAMA_CPP_DIR/CMakeLists.txt" ]; then
        echo "ERROR: Directory exists but doesn't look like llama.cpp repository"
        echo "       (Missing CMakeLists.txt)"
        exit 1
    fi
fi

# Navigate to repo
cd "$LLAMA_CPP_DIR"

# Update to latest (optional, commented out for stability)
# echo "Updating repository..."
# git pull

# Configure with CMake
echo
echo "Configuring build with CMake..."
cmake -S . -B build -DCMAKE_BUILD_TYPE="$BUILD_TYPE"

# Build
echo
echo "Building llama.cpp (this may take several minutes)..."
cmake --build build -j "$BUILD_JOBS"

echo
echo "=================================================="
echo "Build complete!"
echo "=================================================="

# Verify binaries
echo
echo "Verifying binaries..."

QUANTIZE_BIN=""
for candidate in \
    "build/bin/llama-quantize" \
    "build/bin/quantize" \
    "build/llama-quantize" \
    "build/quantize"; do
    
    if [ -x "$LLAMA_CPP_DIR/$candidate" ]; then
        QUANTIZE_BIN="$LLAMA_CPP_DIR/$candidate"
        echo "✓ Found quantize binary: $candidate"
        break
    fi
done

if [ -z "$QUANTIZE_BIN" ]; then
    echo "✗ WARNING: quantize binary not found in expected locations!"
    echo "  Searched:"
    echo "    - build/bin/llama-quantize"
    echo "    - build/bin/quantize"
    echo "    - build/llama-quantize"
    echo "    - build/quantize"
    exit 1
fi

if [ -f "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" ]; then
    echo "✓ Found convert_hf_to_gguf.py"
else
    echo "✗ WARNING: convert_hf_to_gguf.py not found!"
    exit 1
fi

echo
echo "=================================================="
echo "Setup successful!"
echo "=================================================="
echo
echo "To use llama.cpp in your environment, run:"
echo "  export LLAMA_CPP_DIR=\"$LLAMA_CPP_DIR\""
echo
echo "Or add to your ~/.bashrc or ~/.zshrc:"
echo "  export LLAMA_CPP_DIR=\"$LLAMA_CPP_DIR\""
echo
echo "Discovered binaries:"
echo "  Quantize: $QUANTIZE_BIN"
echo "  Convert:  $LLAMA_CPP_DIR/convert_hf_to_gguf.py"
echo
