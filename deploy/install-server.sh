#!/usr/bin/env bash
# UFW OkBoy - Server Installation Script
#
# Run as root on the server:
#   bash install-server.sh

set -euo pipefail

APP_DIR="/opt/ufw-okboy"
DATA_DIR="/var/lib/ufw-okboy"
LOG_DIR="/var/log/ufw-okboy"

echo "=== UFW OkBoy Server Installation ==="

# Check prerequisites
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root."
    exit 1
fi

command -v ufw   >/dev/null 2>&1 || { echo "Error: ufw is not installed."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 is not installed."; exit 1; }

# Create directories
echo "[1/5] Creating directories..."
mkdir -p "$APP_DIR" "$DATA_DIR" "$LOG_DIR"

# Copy application files
echo "[2/5] Copying application files..."
cp -r server/* "$APP_DIR/server/" 2>/dev/null || {
    # If running from repo root
    mkdir -p "$APP_DIR/server"
    cp server/app.py server/ufw_ops.py server/requirements.txt "$APP_DIR/server/"
}

# Create virtual environment and install dependencies
echo "[3/5] Setting up Python virtual environment..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# Config file
echo "[4/5] Setting up configuration..."
if [[ ! -f "$APP_DIR/server/config.yaml" ]]; then
    cp server/config.example.yaml "$APP_DIR/server/config.yaml" 2>/dev/null || \
    cp "$APP_DIR/server/config.example.yaml" "$APP_DIR/server/config.yaml" 2>/dev/null || true
    echo "  -> config.yaml created at $APP_DIR/server/config.yaml"
    echo "  -> IMPORTANT: Edit it and set real user secrets!"
    echo "  -> Generate secrets with: $APP_DIR/venv/bin/python $APP_DIR/server/app.py gen-secret <username>"
else
    echo "  -> config.yaml already exists, skipping."
fi

# Install systemd services
echo "[5/5] Installing systemd services..."
cp deploy/ufw-okboy.service /etc/systemd/system/ 2>/dev/null || true
cp deploy/ufw-okboy-cleanup.service /etc/systemd/system/ 2>/dev/null || true
cp deploy/ufw-okboy-cleanup.timer /etc/systemd/system/ 2>/dev/null || true
systemctl daemon-reload

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit config:    nano $APP_DIR/server/config.yaml"
echo "  2. Generate secrets: $APP_DIR/venv/bin/python $APP_DIR/server/app.py gen-secret alice"
echo "  3. Configure Nginx:  cp nginx/ufw-okboy.conf /etc/nginx/sites-available/"
echo "  4. Start server:     systemctl enable --now ufw-okboy"
echo "  5. Enable cleanup:   systemctl enable --now ufw-okboy-cleanup.timer"
echo "  6. Check status:     systemctl status ufw-okboy"
