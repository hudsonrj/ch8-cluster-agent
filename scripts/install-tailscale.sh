#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# CH8 Agent — Tailscale Auto-Install & Auth
# Installs Tailscale and authenticates using embedded OAuth credentials
# Called automatically by `ch8 up` if Tailscale is not detected
#
# NEVER fails fatally — if incompatible, skips gracefully
# ═══════════════════════════════════════════════════════════════

# Embedded credentials (no external config needed)
TS_CLIENT_ID="kxMbsoMmCf11CNTRL"
TS_CLIENT_SECRET="tskey-client-kxMbsoMmCf11CNTRL-airVftRcWuLcLf41xKvzuLzCUbs7MWdi"

# ── Helper: safe exit (never fatal) ──
fail_gracefully() {
    echo "  [Tailscale] SKIP: $1"
    echo "  [Tailscale] Agent will use LAN IP instead (mesh relay for cross-network)"
    exit 0  # Always exit 0 so ch8 up continues
}

echo "  [Tailscale] Auto-setup starting..."

# ── Check if already connected ──
if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip --4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
        echo "  [Tailscale] Already connected: $TS_IP"
        exit 0
    fi
    echo "  [Tailscale] Installed but not connected. Authenticating..."
fi

# ── Detect OS and architecture ──
OS="unknown"
ARCH=$(uname -m 2>/dev/null || echo "unknown")

if [[ "$OSTYPE" == "linux-gnu"* ]] || [ "$(uname -s)" = "Linux" ]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]] || [ "$(uname -s)" = "Darwin" ]; then
    OS="macos"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    OS="windows"
fi

echo "  [Tailscale] OS=$OS ARCH=$ARCH"

# ── Check prerequisites ──
if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
    fail_gracefully "curl/wget not available — cannot download"
fi

if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    fail_gracefully "python not available — cannot parse OAuth response"
fi

# ── Install if not present ──
if ! command -v tailscale &>/dev/null; then
    echo "  [Tailscale] Installing..."
    case $OS in
        linux)
            # Try official installer (handles all distros + architectures)
            if curl -fsSL https://tailscale.com/install.sh 2>/dev/null | sh 2>&1; then
                echo "  [Tailscale] Installed via official script"
            else
                # Fallback: try apt
                if command -v apt-get &>/dev/null; then
                    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/jammy.gpg 2>/dev/null | sudo apt-key add - 2>/dev/null
                    sudo apt-get install -y tailscale 2>/dev/null || fail_gracefully "apt install failed"
                else
                    fail_gracefully "Linux distro not supported for auto-install"
                fi
            fi
            ;;
        macos)
            if command -v brew &>/dev/null; then
                brew install tailscale 2>/dev/null || fail_gracefully "brew install failed"
            else
                # Try direct download
                echo "  [Tailscale] Downloading macOS package..."
                curl -fsSL "https://pkgs.tailscale.com/stable/tailscale-latest-macos.zip" -o /tmp/tailscale.zip 2>/dev/null
                if [ -f /tmp/tailscale.zip ]; then
                    unzip -o /tmp/tailscale.zip -d /tmp/tailscale 2>/dev/null
                    if [ -d /tmp/tailscale/Tailscale.app ]; then
                        cp -R /tmp/tailscale/Tailscale.app /Applications/ 2>/dev/null || \
                            cp -R /tmp/tailscale/Tailscale.app ~/Applications/ 2>/dev/null || \
                            fail_gracefully "Cannot copy Tailscale.app"
                        open /Applications/Tailscale.app 2>/dev/null || open ~/Applications/Tailscale.app 2>/dev/null
                        echo "  [Tailscale] App installed. Waiting for CLI..."
                        sleep 5
                    else
                        fail_gracefully "Tailscale.app not found in zip"
                    fi
                else
                    fail_gracefully "Download failed — macOS incompatible or no internet"
                fi
            fi
            ;;
        windows)
            fail_gracefully "Windows auto-install not supported. Run: winget install Tailscale.Tailscale"
            ;;
        *)
            fail_gracefully "Unknown OS ($OSTYPE) — cannot auto-install"
            ;;
    esac

    # Verify installation
    if ! command -v tailscale &>/dev/null; then
        fail_gracefully "Installation completed but 'tailscale' command not found in PATH"
    fi
fi

# ── Start daemon if needed (Linux) ──
if [ "$OS" = "linux" ]; then
    if ! pgrep -x tailscaled &>/dev/null; then
        echo "  [Tailscale] Starting daemon..."
        if command -v systemctl &>/dev/null; then
            sudo systemctl start tailscaled 2>/dev/null || \
                sudo tailscaled --state=/var/lib/tailscale/tailscaled.state &>/dev/null &
        else
            sudo tailscaled --state=/var/lib/tailscale/tailscaled.state &>/dev/null &
        fi
        sleep 3
    fi
fi

# ── Authenticate using OAuth credentials ──
echo "  [Tailscale] Authenticating with CH8 network..."

# Get Python command
PY="python3"
command -v python3 &>/dev/null || PY="python"

# Step 1: Get OAuth access token
ACCESS_TOKEN=$($PY -c "
import urllib.request, json
try:
    data = 'client_id=${TS_CLIENT_ID}&client_secret=${TS_CLIENT_SECRET}'.encode()
    req = urllib.request.Request('https://api.tailscale.com/api/v2/oauth/token', data=data)
    resp = urllib.request.urlopen(req, timeout=15)
    print(json.loads(resp.read()).get('access_token', ''))
except Exception as e:
    pass
" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
    fail_gracefully "OAuth token request failed (no internet or invalid credentials)"
fi

# Step 2: Create reusable auth key
AUTH_KEY=$($PY -c "
import urllib.request, json
try:
    data = json.dumps({'capabilities':{'devices':{'create':{'reusable':True,'ephemeral':False,'preauthorized':True}}}}).encode()
    req = urllib.request.Request('https://api.tailscale.com/api/v2/tailnet/-/keys', data=data)
    req.add_header('Authorization', 'Bearer ${ACCESS_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    resp = urllib.request.urlopen(req, timeout=15)
    print(json.loads(resp.read()).get('key', ''))
except Exception as e:
    pass
" 2>/dev/null)

if [ -z "$AUTH_KEY" ]; then
    fail_gracefully "Auth key creation failed"
fi

# Step 3: Connect
echo "  [Tailscale] Connecting to CH8 network..."
HOSTNAME=$(hostname 2>/dev/null || echo "ch8-node")

if sudo tailscale up --authkey="$AUTH_KEY" --hostname="$HOSTNAME" 2>/dev/null; then
    sleep 3
    TS_IP=$(tailscale ip --4 2>/dev/null || echo "")
    if [ -n "$TS_IP" ]; then
        echo "  [Tailscale] ✓ Connected! IP: $TS_IP"
        exit 0
    else
        echo "  [Tailscale] Connected but no IP yet (may take a moment)"
        exit 0
    fi
else
    # Try without sudo (macOS app mode)
    tailscale up --authkey="$AUTH_KEY" --hostname="$HOSTNAME" 2>/dev/null || \
        fail_gracefully "tailscale up failed — may need manual setup"
fi

echo "  [Tailscale] Setup complete"
exit 0
