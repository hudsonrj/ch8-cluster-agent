#!/bin/bash
# CH8 Agent - Linux 32-bit Installation Script
# For i686/i386 systems (old PCs, legacy hardware)
# Usage: curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-32bit.sh | bash

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
  \____|_| |_|\___/   Agent  —  Linux 32-bit
EOF
echo -e "${NC}"

# ── Architecture info ─────────────────────────────────────────────────────
ARCH=$(uname -m)
echo -e "${BLUE}Architecture: $ARCH${NC}"
if [ "$ARCH" != "i686" ] && [ "$ARCH" != "i386" ]; then
    echo -e "${YELLOW}Warning: not detected as 32-bit ($ARCH). For 64-bit use install.sh.${NC}"
fi

RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
echo -e "${BLUE}RAM: ${RAM_MB}MB${NC}"

# ── Check Python 3.10+ ────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${YELLOW}Installing Python3...${NC}"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip git curl
    elif command -v yum &>/dev/null; then
        sudo yum install -y python3 python3-pip git curl
    else
        echo -e "${RED}Cannot install Python3. Install manually and rerun.${NC}"
        exit 1
    fi
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo -e "${RED}Python 3.10+ required, found $PY_VER${NC}"
    echo -e "${YELLOW}Run: sudo apt-get install -y python3.11${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PY_VER${NC}"

if ! command -v git &>/dev/null; then
    command -v apt-get &>/dev/null && sudo apt-get install -y git || true
fi
echo -e "${GREEN}✓ git$(git --version | awk '{print " "$3}')${NC}"

# ── Swap for low-memory systems ───────────────────────────────────────────
if [ "$RAM_MB" -lt 1024 ] && [ ! -f /swapfile ]; then
    echo -e "${YELLOW}Low memory — setting up 1GB swap...${NC}"
    sudo dd if=/dev/zero of=/swapfile bs=1M count=1024 status=progress
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    grep -q "/swapfile" /etc/fstab || echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
    echo -e "${GREEN}✓ Swap configured${NC}"
fi

# ── Install directory ──────────────────────────────────────────────────────
INSTALL_DIR="$HOME/ch8-agent"
echo -e "\n${YELLOW}Install directory:${NC} $INSTALL_DIR"

# ── Clone or update ────────────────────────────────────────────────────────
echo -e "\n${BLUE}Downloading CH8 Agent...${NC}"
mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "${YELLOW}Existing installation found, updating...${NC}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
else
    git clone -b master https://github.com/hudsonrj/ch8-cluster-agent.git "$INSTALL_DIR"
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
elif command -v sudo &>/dev/null; then
    sudo ln -sf "$INSTALL_DIR/ch8" /usr/local/bin/ch8 2>/dev/null || true
    echo -e "${GREEN}✓ Symlink: /usr/local/bin/ch8${NC}"
fi
mkdir -p "$HOME/.config/ch8"

# ── Done ──────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   CH8 Agent installed (32-bit)!       ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "  Arch: ${BLUE}$ARCH${NC}  RAM: ${BLUE}${RAM_MB}MB${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. ${GREEN}source $SHELL_RC${NC}"
echo -e "  2. ${GREEN}ch8 config ai${NC}               (configure AI provider)"
echo -e "  3. ${GREEN}ch8 up --token <TOKEN>${NC}       (join your network)"
echo ""
echo -e "${YELLOW}Recommended AI for low-memory:${NC}"
echo -e "  ${BLUE}Groq${NC}  (cloud, free) — fast, no local GPU needed — groq.com"
echo -e "  ${BLUE}Ollama${NC} (local)      — ollama.com/install.sh"
echo ""
echo -e "${BLUE}Docs: https://github.com/hudsonrj/ch8-cluster-agent${NC}"
echo ""
