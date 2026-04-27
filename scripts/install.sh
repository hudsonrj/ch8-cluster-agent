#!/bin/bash
# CH8 Agent - Installation Script (Linux & macOS)
# Usage: curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash

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
  \____|_| |_|\___/   Agent
EOF
echo -e "${NC}"

echo -e "${GREEN}CH8 Agent — Distributed AI Node System${NC}\n"

# ── Detect OS ──────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    exit 1
fi
echo -e "${BLUE}OS: ${OS}${NC}"

# ── Check Python 3.10+ ────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 not found.${NC}"
    if [ "$OS" == "macos" ]; then
        echo -e "${YELLOW}Install with: brew install python3${NC}"
    else
        echo -e "${YELLOW}Install with: sudo apt install python3 python3-pip${NC}"
    fi
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo -e "${RED}Python 3.10+ required, found $PY_VER${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PY_VER${NC}"

# ── Check git ──────────────────────────────────────────────────────────────
if ! command -v git &> /dev/null; then
    echo -e "${RED}git not found.${NC}"
    if [ "$OS" == "macos" ]; then
        echo -e "${YELLOW}Install with: xcode-select --install${NC}"
    else
        echo -e "${YELLOW}Install with: sudo apt install git${NC}"
    fi
    exit 1
fi
echo -e "${GREEN}✓ git$(git --version | awk '{print " "$3}')${NC}"

# ── Installation directory ─────────────────────────────────────────────────
if [ "$OS" = "macos" ]; then
    INSTALL_DIR="$HOME/ch8-agent"
elif [ -w "/data" ] 2>/dev/null; then
    INSTALL_DIR="/data/ch8-agent"
else
    INSTALL_DIR="$HOME/ch8-agent"
fi

echo -e "\n${YELLOW}Install directory:${NC} $INSTALL_DIR"
read -p "Change? (Enter to confirm, or type new path): " CUSTOM_DIR
if [ -n "$CUSTOM_DIR" ]; then
    INSTALL_DIR="$CUSTOM_DIR"
fi

# ── Clone or update ───────────────────────────────────────────────────────
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

# ── Install Python dependencies ───────────────────────────────────────────
echo -e "\n${BLUE}Installing dependencies...${NC}"
PIP_ARGS="--quiet"
if [ "$OS" == "linux" ]; then
    PIP_ARGS="$PIP_ARGS --break-system-packages"
fi

python3 -m pip install $PIP_ARGS --upgrade pip 2>/dev/null || true
python3 -m pip install $PIP_ARGS \
    httpx psutil fastapi uvicorn pydantic 2>/dev/null

echo -e "${GREEN}✓ Dependencies installed${NC}"

# ── Make ch8 CLI executable and add to PATH ────────────────────────────────
chmod +x "$INSTALL_DIR/ch8"

# Determine shell config file
SHELL_RC=""
if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.bash_profile" ]; then
    SHELL_RC="$HOME/.bash_profile"
fi

# Add to PATH if not already there
if [ -n "$SHELL_RC" ]; then
    if ! grep -q "ch8-agent" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# CH8 Agent" >> "$SHELL_RC"
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$SHELL_RC"
        echo -e "${GREEN}✓ Added to PATH in $SHELL_RC${NC}"
    fi
fi

# Also create symlink if possible
if [ -w "/usr/local/bin" ]; then
    ln -sf "$INSTALL_DIR/ch8" /usr/local/bin/ch8 2>/dev/null || true
    echo -e "${GREEN}✓ Symlink: /usr/local/bin/ch8${NC}"
fi

# ── Create config directory ────────────────────────────────────────────────
mkdir -p "$HOME/.config/ch8"

# ── Done ──────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}╔═══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   CH8 Agent installed successfully!   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}\n"

echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. ${GREEN}source $SHELL_RC${NC}     (reload PATH)"
echo -e "  2. ${GREEN}ch8 config ai${NC}        (configure AI provider)"
echo -e "  3. ${GREEN}ch8 up --token <TOKEN>${NC} (join network)"
echo -e ""
echo -e "${YELLOW}Commands:${NC}"
echo -e "  ${BLUE}ch8 up${NC}              Start agent and join network"
echo -e "  ${BLUE}ch8 down${NC}            Stop agent"
echo -e "  ${BLUE}ch8 status${NC}          Show node status"
echo -e "  ${BLUE}ch8 config ai${NC}       Configure AI provider"
echo -e "  ${BLUE}ch8 config channels${NC} Configure Telegram/Slack"
echo -e "  ${BLUE}ch8 config tools${NC}    Configure agent tools"
echo -e ""
echo -e "${BLUE}Docs: https://github.com/hudsonrj/ch8-cluster-agent${NC}\n"
