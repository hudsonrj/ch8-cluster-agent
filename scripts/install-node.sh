#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# CH8 Agent Node — Installation Script
#
# Installs CH8 agent on a node and connects it to the control server.
# Handles Tailscale setup, dependencies, and network configuration.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-node.sh | bash
#   # or with token:
#   curl -fsSL ... | bash -s -- --token tk_xxx
#   # or locally:
#   bash scripts/install-node.sh --token tk_xxx
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Parse args ────────────────────────────────────────────────────
TOKEN=""
CONTROL_URL=""
SKIP_TAILSCALE=false
ADVERTISE_ADDR=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --token)       TOKEN="$2"; shift 2 ;;
        --control-url) CONTROL_URL="$2"; shift 2 ;;
        --skip-tailscale) SKIP_TAILSCALE=true; shift ;;
        --advertise-addr) ADVERTISE_ADDR="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: install-node.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --token TOKEN          Pre-auth token from the control server"
            echo "  --control-url URL      Control server URL (default: https://control.ch8ai.com.br)"
            echo "  --skip-tailscale       Skip Tailscale installation"
            echo "  --advertise-addr ADDR  Manual IP/hostname for this node"
            echo "  --help                 Show this help"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Colors
R='\033[0m'; B='\033[1m'; RED='\033[0;31m'; GRN='\033[0;32m'
YEL='\033[1;33m'; BLU='\033[0;34m'; CYN='\033[0;36m'; DIM='\033[2m'

header() { echo -e "\n${BLU}${B}[$1]${R} $2"; }
ok()     { echo -e "  ${GRN}✓${R} $1"; }
warn()   { echo -e "  ${YEL}⚠${R} $1"; }
fail()   { echo -e "  ${RED}✗${R} $1"; }

echo -e "${CYN}${B}"
cat << 'LOGO'
   _____ _   _ ___      _                    _
  / ____| | | / _ \    / \   __ _  ___ _ __ | |_
 | |    | |_| | | |   / _ \ / _` |/ _ \ '_ \| __|
 | |___ |  _  | |_|  / ___ \ (_| |  __/ | | | |_
  \____|_| |_|\___/ /_/   \_\__, |\___|_| |_|\__|
                              |___/
      Node Installation
LOGO
echo -e "${R}"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO="${ID:-unknown}"
        DISTRO_VER="${VERSION_ID:-}"
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    DISTRO="macos"
fi

echo -e "  ${DIM}OS: ${OS} (${DISTRO:-unknown} ${DISTRO_VER:-})  Host: $(hostname)${R}"

# ══════════════════════════════════════════════════════════════════
# Step 1: Python
# ══════════════════════════════════════════════════════════════════

header "1/7" "Checking Python 3.10+..."

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$($cmd --version 2>&1 | grep -oP '\d+\.\d+')
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -n "$PYTHON_CMD" ]; then
    ok "Python $($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+\.\d+')"
else
    fail "Python 3.10+ not found"
    if [ "$OS" = "linux" ]; then
        echo -e "    Install: ${CYN}sudo apt install python3 python3-pip python3-venv${R}"
    elif [ "$OS" = "macos" ]; then
        echo -e "    Install: ${CYN}brew install python@3.12${R}"
    fi
    exit 1
fi

# ══════════════════════════════════════════════════════════════════
# Step 2: System dependencies
# ══════════════════════════════════════════════════════════════════

header "2/7" "Checking system dependencies..."

# Git
if command -v git &>/dev/null; then
    ok "Git"
else
    if [ "$OS" = "linux" ]; then
        echo -e "  ${BLU}Installing git...${R}"
        sudo apt-get update -qq && sudo apt-get install -y -qq git && ok "Git installed" || { fail "Git install failed"; exit 1; }
    else
        fail "Git not found — install it first"
        exit 1
    fi
fi

# Docker (optional but recommended)
if command -v docker &>/dev/null; then
    ok "Docker (for container monitoring)"
else
    warn "Docker not found — container monitoring will be disabled"
fi

# psutil dependency (build tools)
if [ "$OS" = "linux" ]; then
    # Ensure pip/venv are available
    $PYTHON_CMD -m pip --version &>/dev/null 2>&1 || {
        echo -e "  ${BLU}Installing python3-pip...${R}"
        sudo apt-get install -y -qq python3-pip python3-venv 2>/dev/null || true
    }
fi

# ══════════════════════════════════════════════════════════════════
# Step 3: Tailscale (network layer)
# ══════════════════════════════════════════════════════════════════

header "3/7" "Network configuration..."

TAILSCALE_OK=false

if [ "$SKIP_TAILSCALE" = true ]; then
    warn "Tailscale skipped (--skip-tailscale)"
else
    if command -v tailscale &>/dev/null; then
        ok "Tailscale installed"
        TS_IP=$(tailscale ip --4 2>/dev/null || true)
        if [ -n "$TS_IP" ]; then
            ok "Tailscale connected: ${TS_IP}"
            TAILSCALE_OK=true
        else
            warn "Tailscale installed but not connected"
            echo -e "    Run: ${CYN}sudo tailscale up${R}"
            echo ""
            read -p "  Connect Tailscale now? [Y/n] " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                sudo tailscale up 2>/dev/null && {
                    TS_IP=$(tailscale ip --4 2>/dev/null || true)
                    [ -n "$TS_IP" ] && ok "Tailscale connected: ${TS_IP}" && TAILSCALE_OK=true
                } || warn "Tailscale connection failed"
            fi
        fi
    else
        echo -e "  ${BLU}Tailscale enables secure cross-network communication.${R}"
        echo ""
        echo -e "  ${B}Options:${R}"
        echo -e "    ${GRN}1${R}) Install Tailscale now (recommended)"
        echo -e "    ${YEL}2${R}) Skip — use LAN IP or manual address"
        echo -e "    ${YEL}3${R}) Skip — I'll configure WireGuard/VPN separately"
        echo ""
        read -p "  Choose [1/2/3]: " -n 1 -r TS_CHOICE
        echo

        case "${TS_CHOICE:-1}" in
            1)
                echo -e "  ${BLU}Installing Tailscale...${R}"
                if [ "$OS" = "linux" ]; then
                    curl -fsSL https://tailscale.com/install.sh | sh 2>/dev/null && {
                        ok "Tailscale installed"
                        echo -e "  ${BLU}Connecting to Tailscale network...${R}"
                        sudo tailscale up 2>/dev/null && {
                            TS_IP=$(tailscale ip --4 2>/dev/null || true)
                            [ -n "$TS_IP" ] && ok "Tailscale connected: ${TS_IP}" && TAILSCALE_OK=true
                        } || warn "Connect manually: sudo tailscale up"
                    } || {
                        warn "Tailscale install failed — continuing without it"
                    }
                elif [ "$OS" = "macos" ]; then
                    echo -e "    Install from: ${CYN}https://tailscale.com/download/mac${R}"
                    echo -e "    Then run: ${CYN}tailscale up${R}"
                fi
                ;;
            2|3)
                warn "Skipping Tailscale"
                ;;
        esac
    fi
fi

# Network summary
if [ "$TAILSCALE_OK" = true ]; then
    echo -e "\n  ${GRN}${B}Network: Tailscale mesh${R} (${TS_IP})"
elif [ -n "$ADVERTISE_ADDR" ]; then
    echo -e "\n  ${YEL}${B}Network: Manual address${R} (${ADVERTISE_ADDR})"
else
    # Detect LAN IP
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
    echo -e "\n  ${YEL}${B}Network: LAN only${R} (${LAN_IP})"
    echo -e "  ${DIM}Nodes on other networks won't be able to reach this node.${R}"
    echo -e "  ${DIM}Set CH8_ADVERTISE_ADDR or install Tailscale for cross-network.${R}"
fi

# ══════════════════════════════════════════════════════════════════
# Step 4: Clone / update CH8 agent
# ══════════════════════════════════════════════════════════════════

header "4/7" "Installing CH8 agent..."

DEFAULT_DIR="/data/ch8-agent"
read -p "  Install path [${DEFAULT_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

if [ -d "${INSTALL_DIR}/.git" ]; then
    ok "Repository exists, pulling updates..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone https://github.com/hudsonrj/ch8-cluster-agent.git "$INSTALL_DIR" 2>/dev/null || {
        if [ -d "$INSTALL_DIR" ]; then
            warn "Git clone failed, using existing files"
        else
            fail "Could not clone repository"
            exit 1
        fi
    }
fi

cd "$INSTALL_DIR"
ok "CH8 agent at ${INSTALL_DIR}"

# ══════════════════════════════════════════════════════════════════
# Step 5: Python dependencies
# ══════════════════════════════════════════════════════════════════

header "5/7" "Installing Python dependencies..."

# Install core dependencies (no venv — system-wide for simplicity)
DEPS="httpx psutil fastapi uvicorn pydantic"

$PYTHON_CMD -m pip install --quiet --break-system-packages $DEPS 2>/dev/null || \
$PYTHON_CMD -m pip install --quiet $DEPS 2>/dev/null || {
    fail "Dependency installation failed"
    echo -e "    Try: ${CYN}$PYTHON_CMD -m pip install httpx psutil fastapi uvicorn pydantic${R}"
    exit 1
}

ok "Core dependencies: httpx, psutil, fastapi, uvicorn, pydantic"

# Ollama check (optional)
if command -v ollama &>/dev/null; then
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ', ' | sed 's/,$//')
    ok "Ollama found — models: ${MODELS:-none}"
else
    warn "Ollama not found — no local LLM available"
    echo -e "    Install for AI capabilities: ${CYN}https://ollama.com/download${R}"
fi

# ══════════════════════════════════════════════════════════════════
# Step 6: Configure and connect
# ══════════════════════════════════════════════════════════════════

header "6/7" "Configuring CH8 agent..."

# Make CLI executable
chmod +x "${INSTALL_DIR}/ch8"

# Add to PATH
SHELL_RC=""
[ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"
[ -f "$HOME/.zshrc" ]  && SHELL_RC="$HOME/.zshrc"

if [ -n "$SHELL_RC" ]; then
    if ! grep -q "ch8-agent" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# CH8 Agent" >> "$SHELL_RC"
        echo "export PATH=\"\$PATH:${INSTALL_DIR}\"" >> "$SHELL_RC"
        ok "Added to PATH in ${SHELL_RC}"
    else
        ok "Already in PATH"
    fi
fi

# Ensure ch8 is available in current session
export PATH="$PATH:${INSTALL_DIR}"

# Control server URL
if [ -z "$CONTROL_URL" ]; then
    DEFAULT_CONTROL="https://control.ch8ai.com.br"
    read -p "  Control server URL [${DEFAULT_CONTROL}]: " CONTROL_URL
    CONTROL_URL="${CONTROL_URL:-$DEFAULT_CONTROL}"
fi

# Write environment config
ENV_FILE="${HOME}/.config/ch8/env"
mkdir -p "$(dirname "$ENV_FILE")"
cat > "$ENV_FILE" << ENV_EOF
# CH8 Agent configuration
CH8_CONTROL_URL=${CONTROL_URL}
ENV_EOF

if [ -n "$ADVERTISE_ADDR" ]; then
    echo "CH8_ADVERTISE_ADDR=${ADVERTISE_ADDR}" >> "$ENV_FILE"
fi

# Export for current session
export CH8_CONTROL_URL="$CONTROL_URL"
[ -n "$ADVERTISE_ADDR" ] && export CH8_ADVERTISE_ADDR="$ADVERTISE_ADDR"

ok "Control server: ${CONTROL_URL}"

# ══════════════════════════════════════════════════════════════════
# Step 7: Connect to network
# ══════════════════════════════════════════════════════════════════

header "7/7" "Connecting to CH8 network..."

if [ -z "$TOKEN" ]; then
    echo -e "  ${B}To connect this node, you need a pre-auth token from the control server.${R}"
    echo ""
    echo -e "  Get one by running on an authenticated machine:"
    echo -e "    ${CYN}ch8 token create${R}"
    echo -e "  Or from the control server directly:"
    echo -e "    ${CYN}curl -X POST http://localhost:8081/api/admin/bootstrap${R}"
    echo ""
    read -p "  Enter token (or press Enter to skip): " TOKEN
fi

if [ -n "$TOKEN" ]; then
    echo -e "  ${BLU}Connecting...${R}"
    cd "$INSTALL_DIR"
    $PYTHON_CMD ch8 up --token "$TOKEN" && {
        ok "Node connected to CH8 network!"
    } || {
        warn "Connection failed — try manually: ch8 up --token $TOKEN"
    }
else
    warn "Skipped — connect later with: ch8 up --token <TOKEN>"
fi

# ══════════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════════

echo ""
echo -e "${GRN}${B}╔═══════════════════════════════════════════════════════════╗${R}"
echo -e "${GRN}${B}║  CH8 Agent Node — Installation Complete                  ║${R}"
echo -e "${GRN}${B}╚═══════════════════════════════════════════════════════════╝${R}"
echo ""
echo -e "  ${B}Install path:${R}  ${INSTALL_DIR}"
echo -e "  ${B}Control URL:${R}   ${CONTROL_URL}"
echo -e "  ${B}Network:${R}       ${TAILSCALE_OK:+Tailscale (${TS_IP:-?})}${ADVERTISE_ADDR:+Manual (${ADVERTISE_ADDR})}${TAILSCALE_OK:-${ADVERTISE_ADDR:-LAN only}}"
echo ""
echo -e "  ${B}Commands:${R}"
echo -e "    ${YEL}ch8 up --token TOKEN${R}   Connect to network"
echo -e "    ${YEL}ch8 down${R}               Disconnect"
echo -e "    ${YEL}ch8 nodes${R}              List all nodes"
echo -e "    ${YEL}ch8 token create${R}       Create token for other nodes"
echo -e "    ${YEL}ch8 help${R}               Show all commands"
echo ""

if [ -n "$SHELL_RC" ]; then
    echo -e "  ${DIM}Run: source ${SHELL_RC}  (to update PATH in current session)${R}"
fi
echo ""
