#!/bin/bash
# Setup systemd service for ADS-B Ingestion

set -e

echo "Setting up systemd service..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Copy service file
cp systemd/adsb-ingestion.service /etc/systemd/system/

# Reload systemd
systemctl daemon-reload

# Enable service
systemctl enable adsb-ingestion.service

echo ""
echo "Systemd service installed and enabled!"
echo ""
echo "Available commands:"
echo "  Start:   sudo systemctl start adsb-ingestion"
echo "  Stop:    sudo systemctl stop adsb-ingestion"
echo "  Status:  sudo systemctl status adsb-ingestion"
echo "  Logs:    sudo journalctl -u adsb-ingestion -f"
echo ""