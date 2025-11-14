#!/bin/bash
# Installation script for ADS-B Ingestion Service

set -e

echo "=================================="
echo "ADS-B Ingestion Service Installer"
echo "=================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Variables
INSTALL_DIR="/opt/adsb-ingestion"
CONFIG_DIR="/etc/adsb-ingestion"
LOG_DIR="/var/log/adsb-ingestion"
SERVICE_USER="adsb"

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv mariadb-client-compat

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    echo "Creating service user: $SERVICE_USER"
    useradd -r -s /bin/false -d $INSTALL_DIR $SERVICE_USER
fi

# Create directories
echo "Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $CONFIG_DIR
mkdir -p $LOG_DIR

# Copy application files
echo "Copying application files..."
cp -r src/* $INSTALL_DIR/
cp requirements.txt $INSTALL_DIR/
cp config/config.yaml.example $CONFIG_DIR/config.yaml

# Create virtual environment
echo "Creating Python virtual environment..."
cd $INSTALL_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Set permissions
echo "Setting permissions..."
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
chown -R $SERVICE_USER:$SERVICE_USER $LOG_DIR
chmod 755 $INSTALL_DIR
chmod 755 $CONFIG_DIR
chmod 755 $LOG_DIR
chmod 644 $CONFIG_DIR/config.yaml

# Make main script executable
chmod +x $INSTALL_DIR/main.py

echo ""
echo "Installation complete!"
echo ""
echo "Next steps:"
echo "1. Configure the service: sudo nano $CONFIG_DIR/config.yaml"
echo "2. Setup database: mysql -u root -p < database/schema.sql"
echo "3. Install systemd service: sudo ./scripts/setup_service.sh"
echo "4. Start service: sudo systemctl start adsb-ingestion"
echo ""