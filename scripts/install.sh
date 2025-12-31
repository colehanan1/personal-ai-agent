#!/bin/bash
set -e

echo "========================================"
echo "Milton Orchestrator Installation"
echo "========================================"
echo ""

# Detect installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Installation directory: $INSTALL_DIR"

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "Error: conda not found. Please install miniconda/anaconda first."
    exit 1
fi

# Check if milton conda env exists
if ! conda env list | grep -q "^milton "; then
    echo "Error: conda environment 'milton' not found."
    echo "Please create it first with:"
    echo "  conda create -n milton python=3.12"
    exit 1
fi

echo "Using conda environment: milton"

# Activate conda environment
eval "$(conda shell.bash hook)"
conda activate milton

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip wheel setuptools

# Install package in editable mode with dev dependencies
echo "Installing milton-orchestrator..."
pip install -e "$INSTALL_DIR[dev]"

echo ""
echo "========================================"
echo "Installation complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and configure it:"
echo "   cp $INSTALL_DIR/.env.example $INSTALL_DIR/.env"
echo "   nano $INSTALL_DIR/.env"
echo ""
echo "2. Install systemd user service (optional):"
echo "   $INSTALL_DIR/scripts/install-service.sh"
echo ""
echo "3. Test the installation:"
echo "   conda activate milton"
echo "   milton-orchestrator --help"
echo ""
echo "4. Run tests:"
echo "   conda activate milton"
echo "   pytest"
echo ""
