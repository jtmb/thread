#!/usr/bin/env bash
set -euo pipefail

# Thread — Raspberry Pi 3B Deployment Script
# Sets up the Thread AI context server from scratch.
# Run this on the Pi after cloning the repository.
#
# Usage:
#   chmod +x deploy/setup.sh
#   ./deploy/setup.sh
#
# Environment variables (optional overrides):
#   THREAD_DIR — install directory (default: /home/pi/thread-server)
#   THREAD_PORT — server port (default: 5000)
#   THREAD_POOL_SIZE — thread pool size (default: 12)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
THREAD_DIR="${THREAD_DIR:-/home/pi/thread-server}"
THREAD_PORT="${THREAD_PORT:-5000}"
THREAD_POOL_SIZE="${THREAD_POOL_SIZE:-12}"

echo "=== Thread Server Deployment ==="
echo ""
echo "Install directory: $THREAD_DIR"
echo "Port:              $THREAD_PORT"
echo "Thread pool:       $THREAD_POOL_SIZE"
echo ""

# ── Step 1: Create directory structure ─────────────────────────────────────
echo ">>> Step 1: Creating directory structure..."
sudo mkdir -p "$THREAD_DIR"
sudo mkdir -p "$THREAD_DIR/data"
sudo mkdir -p "$THREAD_DIR/data/git"
sudo chown -R pi:pi "$THREAD_DIR"
echo "    Directory structure created at $THREAD_DIR"

# ── Step 2: Copy server files ─────────────────────────────────────────────
echo ""
echo ">>> Step 2: Copying server files..."

# Copy thread_server package
if [[ -d "thread_server" ]]; then
    cp -r thread_server "$THREAD_DIR/"
    echo "    Copied thread_server/"
else
    echo "    ERROR: thread_server/ directory not found. Run from repo root."
    exit 1
fi

# Copy thread_bridge package (optional — workstation side)
if [[ -d "thread_bridge" ]]; then
    cp -r thread_bridge "$THREAD_DIR/"
    echo "    Copied thread_bridge/"
fi

# Copy data directory if pre-populated
if [[ -d "data" ]] && [[ -n "$(ls -A data 2>/dev/null || true)" ]]; then
    cp -r data/* "$THREAD_DIR/data/" 2>/dev/null || true
    echo "    Copied data/"
fi

# ── Step 3: Set up Python virtual environment ──────────────────────────────
echo ""
echo ">>> Step 3: Setting up Python virtual environment..."

if ! command -v python3 &>/dev/null; then
    echo "    ERROR: python3 not found. Install with: sudo apt install python3 python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "    Python version: $PYTHON_VERSION"

if [[ ! -d "$THREAD_DIR/venv" ]]; then
    python3 -m venv "$THREAD_DIR/venv"
    echo "    Virtual environment created"
else
    echo "    Virtual environment already exists"
fi

# Activate and upgrade pip
# shellcheck disable=SC1090
source "$THREAD_DIR/venv/bin/activate"
pip install --upgrade pip --quiet

# ── Step 4: Install Python dependencies ────────────────────────────────────
echo ""
echo ">>> Step 4: Installing Python dependencies..."

if [[ -f "$THREAD_DIR/thread_server/requirements.txt" ]]; then
    pip install -r "$THREAD_DIR/thread_server/requirements.txt" --quiet
    echo "    Dependencies installed"
else
    # Fallback: install minimum requirements
    pip install "flask>=3.0,<4.0" "waitress>=3.0,<4.0" "requests>=2.31,<3.0" --quiet
    echo "    Dependencies installed (fallback)"
fi

deactivate

# ── Step 5: Copy and enable systemd service ────────────────────────────────
echo ""
echo ">>> Step 5: Setting up systemd service..."

SERVICE_FILE="$THREAD_DIR/deploy/thread.service"
TARGET_SERVICE="/etc/systemd/system/thread.service"

if [[ -f "$SERVICE_FILE" ]]; then
    # Update paths in service file
    sudo cp "$SERVICE_FILE" "$TARGET_SERVICE"
    sudo sed -i "s|WorkingDirectory=/home/pi/thread-server|WorkingDirectory=$THREAD_DIR|g" "$TARGET_SERVICE"
    sudo sed -i "s|ExecStart=/home/pi/thread-server|ExecStart=$THREAD_DIR|g" "$TARGET_SERVICE"
    sudo sed -i "s|ReadWritePaths=/home/pi/thread-server/data|ReadWritePaths=$THREAD_DIR/data|g" "$TARGET_SERVICE"
    sudo sed -i "s|ReadOnlyPaths=/home/pi/thread-server/thread_server|ReadOnlyPaths=$THREAD_DIR/thread_server|g" "$TARGET_SERVICE"
    sudo sed -i "s|ReadOnlyPaths=/home/pi/thread-server/venv|ReadOnlyPaths=$THREAD_DIR/venv|g" "$TARGET_SERVICE"
    sudo sed -i "s|THREAD_PORT=5000|THREAD_PORT=$THREAD_PORT|g" "$TARGET_SERVICE"
    sudo sed -i "s|THREAD_POOL_SIZE=12|THREAD_POOL_SIZE=$THREAD_POOL_SIZE|g" "$TARGET_SERVICE"
    sudo sed -i "s|THREAD_DB_PATH=/home/pi/thread-server/data/thread.db|THREAD_DB_PATH=$THREAD_DIR/data/thread.db|g" "$TARGET_SERVICE"
    sudo sed -i "s|THREAD_GIT_BASE=/home/pi/thread-server/data/git|THREAD_GIT_BASE=$THREAD_DIR/data/git|g" "$TARGET_SERVICE"
    echo "    Service file installed at $TARGET_SERVICE"
else
    echo "    WARNING: deploy/thread.service not found. Skipping systemd setup."
    echo "    Create the service file manually or run from the repo root."
fi

# ── Step 6: Reload systemd and enable service ──────────────────────────────
echo ""
echo ">>> Step 6: Enabling service..."

if [[ -f "$TARGET_SERVICE" ]]; then
    sudo systemctl daemon-reload
    sudo systemctl enable thread.service

    # Stop if already running, then start fresh
    if systemctl is-active --quiet thread.service; then
        echo "    Stopping existing service..."
        sudo systemctl stop thread.service
    fi

    sudo systemctl start thread.service
    echo "    Service started"
else
    echo "    SKIPPED — no service file installed"
fi

# ── Step 7: Show status ────────────────────────────────────────────────────
echo ""
echo "=== Deployment Complete ==="
echo ""

if systemctl is-active --quiet thread.service 2>/dev/null; then
    echo "Service status: ACTIVE"
    echo ""
    echo "Check logs:"
    echo "  sudo journalctl -u thread.service -f"
    echo ""
    echo "Test health:"
    echo "  curl http://localhost:$THREAD_PORT/api/v1/health"
    echo ""
    sudo systemctl status thread.service --no-pager --lines=10 2>/dev/null || true
else
    echo "Service status: NOT RUNNING"
    echo "Check logs: sudo journalctl -u thread.service"
    echo "Start manually: sudo systemctl start thread.service"
fi

echo ""
echo "=== Done ==="
