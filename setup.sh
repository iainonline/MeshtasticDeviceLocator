#!/bin/bash
# Setup script for GPS Reader on Raspberry Pi 5

echo "Setting up GPS Reader application..."

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✓ Setup complete!"
echo ""
echo "To use the application:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Run the GPS reader:"
echo "   python gps_client.py --host <your-phone-ip>"
echo ""
echo "Example:"
echo "   python gps_client.py --host 192.168.1.50"
