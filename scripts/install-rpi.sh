#!/bin/bash
# CH8 Agent - Raspberry Pi Installation Script
# Supports: Pi Zero 2W, Pi 2, Pi 3, Pi 4, Pi 5
# Usage: curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-rpi.sh | bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
cat << "EOF"
   _____ _   _ ___
  / ____| | | ( _ )
 | |    | |_| / _ \
 | |___ |  _  | (_) |
  \____|_| |_|\___/   Agent  —  Raspberry Pi
EOF
echo -e "${NC}"

# ── Detect Raspberry Pi ────────────────────────────────────────────────────
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${YELLOW}Warning: /proc/device-tree/model not found — may not be a Raspberry Pi${NC}"
    echo -e "${YELLOW}  Continuing with generic ARM Linux install...${NC}"
    PI_MODEL="Unknown ARM device"
else
    PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
    echo -e "${GREEN}Detected: $PI_MODEL${NC}"
fi

RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
echo -e "${BLUE}RAM: ${RAM_MB}MB${NC}"

# ── Ensure Python 3.10+ ───────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${YELLOW}Installing Python3...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip git curl
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo -e "${RED}Python 3.10+ required, found $PY_VER${NC}"
    echo -e "${YELLOW}Run: sudo apt-get install -y python3.11${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PY_VER${NC}"

if ! command -v git &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y git
fi
echo -e "${GREEN}✓ git$(git --version | awk '{print " "$3}')${NC}"

# ── Swap for low-memory devices ───────────────────────────────────────────
if [ "$RAM_MB" -lt 2048 ]; then
    SWAP_SIZE=$((RAM_MB * 2))
    if [ ! -f /swapfile ]; then
        echo -e "${YELLOW}Setting up ${SWAP_SIZE}MB swap (low-memory device)...${NC}"
        sudo dd if=/dev/zero of=/swapfile bs=1M count=$SWAP_SIZE status=progress
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
        sudo swapon /swapfile
        grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
        echo -e "${GREEN}✓ Swap ${SWAP_SIZE}MB configured${NC}"
    else
        echo -e "${YELLOW}Swap already configured${NC}"
    fi
fi

# ── Install directory ──────────────────────────────────────────────────────
if [ -w "/data" ]; then
    INSTALL_DIR="/data/ch8-agent"
else
    INSTALL_DIR="$HOME/ch8-agent"
fi
echo -e "\n${YELLOW}Install directory:${NC} $INSTALL_DIR"

# ── Clone or update ────────────────────────────────────────────────────────
echo -e "\n${BLUE}Downloading CH8 Agent...${NC}"
mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}Existing installation found, updating...${NC}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    git clone https://github.com/hudsonrj/ch8-cluster-agent.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── Install Python dependencies ────────────────────────────────────────────
echo -e "\n${BLUE}Installing dependencies...${NC}"
python3 -m pip install --quiet --upgrade pip 2>/dev/null || true
python3 -m pip install --quiet --break-system-packages \
    httpx psutil fastapi uvicorn pydantic 2>/dev/null || \
python3 -m pip install --quiet \
    httpx psutil fastapi uvicorn pydantic 2>/dev/null || true
echo -e "${GREEN}✓ Dependencies installed${NC}"

# ── CLI and PATH ───────────────────────────────────────────────────────────
chmod +x "$INSTALL_DIR/ch8"

SHELL_RC="$HOME/.bashrc"
[ -f "$HOME/.bash_profile" ] && SHELL_RC="$HOME/.bash_profile"

if ! grep -q "ch8-agent" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# CH8 Agent" >> "$SHELL_RC"
    echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$SHELL_RC"
    echo -e "${GREEN}✓ Added to PATH in $SHELL_RC${NC}"
fi

if [ -w "/usr/local/bin" ]; then
    ln -sf "$INSTALL_DIR/ch8" /usr/local/bin/ch8 2>/dev/null || true
    echo -e "${GREEN}✓ Symlink: /usr/local/bin/ch8${NC}"
fi

mkdir -p "$HOME/.config/ch8"

# ── Systemd user service (optional autostart) ─────────────────────────────
if command -v systemctl &>/dev/null && [ "$EUID" -ne 0 ]; then
    SERVICE_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_DIR/ch8-agent.service" << SVCEOF
[Unit]
Description=CH8 Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$INSTALL_DIR/ch8 up
ExecStop=$INSTALL_DIR/ch8 down

[Install]
WantedBy=default.target
SVCEOF
    systemctl --user daemon-reload 2>/dev/null || true
    echo -e "${GREEN}✓ Systemd user service created${NC}"
fi

# ── Done ──────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   CH8 Agent installed on Pi!          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Device: ${BLUE}$PI_MODEL${NC}"
echo -e "  RAM:    ${BLUE}${RAM_MB}MB${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. ${GREEN}source $SHELL_RC${NC}"
echo -e "  2. ${GREEN}ch8 config ai${NC}               (configure AI provider)"
echo -e "  3. ${GREEN}ch8 up --token <TOKEN>${NC}       (join your network)"
echo ""
echo -e "${YELLOW}Commands:${NC}"
echo -e "  ${BLUE}ch8 up${NC}        Start agent and join network"
echo -e "  ${BLUE}ch8 down${NC}      Stop agent"
echo -e "  ${BLUE}ch8 status${NC}    Node status and peers"
echo ""
echo -e "${YELLOW}Autostart on boot:${NC}"
echo -e "  ${GREEN}systemctl --user enable ch8-agent${NC}"
echo -e "  ${GREEN}loginctl enable-linger \$USER${NC}"
echo ""
echo -e "${YELLOW}AI options for Pi:${NC}"
echo -e "  ${BLUE}Ollama${NC} (local)  — curl -fsSL https://ollama.com/install.sh | sh"
echo -e "  ${BLUE}Groq${NC}  (cloud)  — free API, fast, ideal for Pi — groq.com"
echo ""
echo -e "${BLUE}Docs: https://github.com/hudsonrj/ch8-cluster-agent${NC}"
echo ""
