#!/bin/bash
# CH8 Agent — Restart script (called after git pull during update)
# This file is ALWAYS the latest version after git pull
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CH8="$REPO_DIR/ch8"
LOG="$REPO_DIR/update.log"
PYTHON="${PYTHON:-python3}"

echo "[UPDATE] Restart at $(date '+%H:%M:%S')" >> "$LOG"

# Configure Ollama to listen on all interfaces (required for benchmark/cross-cluster access)
if systemctl is-active ollama > /dev/null 2>&1 || command -v ollama > /dev/null 2>&1; then
    mkdir -p /etc/systemd/system/ollama.service.d
    printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' \
        > /etc/systemd/system/ollama.service.d/override.conf
    systemctl daemon-reload > /dev/null 2>&1 || true
    systemctl restart ollama > /dev/null 2>&1 || true
    echo "[UPDATE] Ollama configured to listen on 0.0.0.0:11434" >> "$LOG"
fi

# Full stop
"$PYTHON" "$CH8" down >> "$LOG" 2>&1 || true
sleep 3

# Fresh start with new code
"$PYTHON" "$CH8" up >> "$LOG" 2>&1 || true
sleep 5

# Health check
if curl -s --max-time 5 http://127.0.0.1:7879/health > /dev/null 2>&1; then
    echo "[UPDATE] OK — orchestrator healthy" >> "$LOG"
else
    echo "[UPDATE] WARNING — orchestrator not responding" >> "$LOG"
fi
