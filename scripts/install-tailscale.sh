#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# CH8 Agent — Tailscale Auto-Install & Auth
# Installs Tailscale and authenticates using OAuth credentials
# Called automatically by `ch8 up` if Tailscale is not detected
# ═══════════════════════════════════════════════════════════════

set -e

TS_CLIENT_ID="kxMbsoMmCf11CNTRL"
TS_CLIENT_SECRET="tskey-client-kxMbsoMmCf11CNTRL-airVftRcWuLcLf41xKvzuLzCUbs7MWdi"

echo "  [Tailscale] Checking installation..."

# ── Detect OS ──
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    OS="windows"
fi

# ── Check if already installed ──
if command -v tailscale &>/dev/null; then
    echo "  [Tailscale] Already installed: $(tailscale version 2>/dev/null | head -1)"
    # Check if connected
    if tailscale status &>/dev/null; then
        TS_IP=$(tailscale ip --4 2>/dev/null || echo "")
        if [ -n "$TS_IP" ]; then
            echo "  [Tailscale] Connected: $TS_IP"
            exit 0
        fi
    fi
    echo "  [Tailscale] Installed but not connected. Authenticating..."
else
    # ── Install ──
    echo "  [Tailscale] Installing for $OS..."
    case $OS in
        linux)
            curl -fsSL https://tailscale.com/install.sh | sh
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install tailscale
            else
                echo "  [Tailscale] ERROR: brew not found. Install manually: https://tailscale.com/download"
                exit 1
            fi
            ;;
        windows)
            echo "  [Tailscale] Windows detected. Install from: https://tailscale.com/download/windows"
            echo "  Or run: winget install Tailscale.Tailscale"
            exit 1
            ;;
        *)
            echo "  [Tailscale] Unknown OS. Install manually: https://tailscale.com/download"
            exit 1
            ;;
    esac
    echo "  [Tailscale] Installed successfully"
fi

# ── Start daemon if needed (Linux) ──
if [ "$OS" = "linux" ]; then
    if ! pgrep -x tailscaled &>/dev/null; then
        echo "  [Tailscale] Starting tailscaled..."
        sudo tailscaled --state=/var/lib/tailscale/tailscaled.state &>/dev/null &
        sleep 2
    fi
fi

# ── Authenticate using OAuth ──
echo "  [Tailscale] Authenticating with CH8 network..."

# Step 1: Get access token from OAuth credentials
ACCESS_TOKEN=$(curl -s -d "client_id=${TS_CLIENT_ID}&client_secret=${TS_CLIENT_SECRET}" \
    "https://api.tailscale.com/api/v2/oauth/token" | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    echo "  [Tailscale] ERROR: Failed to get OAuth token"
    exit 1
fi

# Step 2: Create a reusable auth key
AUTH_KEY=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d '{"capabilities":{"devices":{"create":{"reusable":true,"ephemeral":false,"preauthorized":true}}}}' \
    "https://api.tailscale.com/api/v2/tailnet/-/keys" | python3 -c "import sys,json;print(json.load(sys.stdin).get('key',''))" 2>/dev/null)

if [ -z "$AUTH_KEY" ]; then
    echo "  [Tailscale] ERROR: Failed to create auth key"
    exit 1
fi

# Step 3: Connect with the auth key
echo "  [Tailscale] Connecting to network..."
sudo tailscale up --authkey="$AUTH_KEY" --hostname="$(hostname)" 2>/dev/null || \
    tailscale up --authkey="$AUTH_KEY" --hostname="$(hostname)" 2>/dev/null

# Step 4: Verify
sleep 3
TS_IP=$(tailscale ip --4 2>/dev/null || echo "")
if [ -n "$TS_IP" ]; then
    echo "  [Tailscale] ✓ Connected! IP: $TS_IP"
else
    echo "  [Tailscale] WARNING: Connected but no IPv4 yet. May take a moment."
fi
