#!/bin/bash
# Installation script for Mesh Tracker improvements
# Creates virtual environment and installs dependencies

echo "=================================================="
echo "Mesh Tracker Improvements - Installation"
echo "=================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo ""

# Upgrade pip
echo "Upgrading pip in virtual environment..."
pip install --upgrade pip
echo ""

# Install dependencies
echo "Installing dependencies..."
echo "  - numpy (array operations)"
echo "  - scipy (optimization)"
echo "  - filterpy (Kalman filtering)"
echo "  - rich (terminal UI)"
echo "  - meshtastic (device communication)"
echo "  - gps3 (GPS parsing)"
echo ""

pip install -r requirements.txt

echo ""
echo "=================================================="
echo "Installation complete!"
echo "=================================================="
echo ""

# Run test script
echo "Running validation tests..."
python test_improvements.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ All tests passed!"
    echo ""
    echo "To use the tracker:"
    echo "  1. Activate virtual environment: source venv/bin/activate"
    echo "  2. Run tracker: python mesh_tracker.py"
    echo "  3. Deactivate when done: deactivate"
    echo ""
    echo "Or use the run script: ./run.sh"
    echo ""
    echo "For usage examples, see: QUICKSTART.md"
else
    echo ""
    echo "⚠ Some tests failed. Check error messages above."
    echo "You may need to manually install dependencies:"
    echo "  source venv/bin/activate"
    echo "  pip install numpy scipy filterpy"
fi
echo ""
echo "Virtual environment is active. Type 'deactivate' to exit."
