#!/bin/bash
set -e

echo "========================================"
echo "Milton Orchestrator Installation"
echo "========================================"
echo ""

# Detect installation directory
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Installation directory: $INSTALL_DIR"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Error: Python 3.11 or higher is required"
    exit 1
fi

# Create virtual environment
VENV_DIR="$INSTALL_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR"
    read -p "Remove and recreate? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
    else
        echo "Using existing virtual environment"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

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
echo "   source $VENV_DIR/bin/activate"
echo "   milton-orchestrator --help"
echo ""
echo "4. Run tests:"
echo "   source $VENV_DIR/bin/activate"
echo "   pytest"
echo ""
