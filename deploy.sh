#!/usr/bin/env bash
set -euo pipefail

HOST="pi@hoardicult"
APP_DIR="/home/pi/hoardicult"
SERVICE="hoardicult"

echo "Deploying to $HOST..."

ssh "$HOST" bash <<'EOF'
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd /home/pi/hoardicult

echo "Pulling latest code..."
git pull --ff-only

echo "Installing dependencies..."
uv sync

echo "Restarting service..."
sudo systemctl restart hoardicult

sleep 2
if systemctl is-active --quiet hoardicult; then
    echo "Deploy complete — hoardicult is running."
else
    echo "ERROR: hoardicult failed to start!" >&2
    journalctl -u hoardicult --no-pager -n 10
    exit 1
fi
EOF
