#!/data/data/com.termux/files/usr/bin/bash
# CH8 Agent - Android/Termux Installation Script
# Usage: curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-android.sh | bash

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
  \____|_| |_|\___/   Agent  -  Android/Termux
EOF
echo -e "${NC}"

# ── Check we're in Termux ─────────────────────────────────────────────────
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${RED}This script must be run inside Termux.${NC}"
    echo -e "${YELLOW}Download Termux from: https://f-droid.org/en/packages/com.termux/${NC}"
    echo -e "${YELLOW}(Do NOT use the Play Store version — it's outdated)${NC}"
    exit 1
fi

echo -e "${GREEN}Running in Termux on Android${NC}\n"

# ── Update packages and install dependencies ──────────────────────────────
echo -e "${BLUE}[1/4] Installing system packages...${NC}"
pkg update -y 2>/dev/null
pkg install -y python git 2>/dev/null

# Check Python version
PYTHON_VER=$(python3 --version 2>/dev/null | grep -oP '\d+\.\d+' | head -1)
MAJOR=$(echo "$PYTHON_VER" | cut -d. -f1)
MINOR=$(echo "$PYTHON_VER" | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo -e "${RED}Python 3.10+ required. Got: $PYTHON_VER${NC}"
    exit 1
fi
echo -e "  ${GREEN}[OK] Python $PYTHON_VER${NC}"

# ── Install Python packages ───────────────────────────────────────────────
echo -e "${BLUE}[2/4] Installing Python dependencies...${NC}"
pip install --quiet --upgrade pip 2>/dev/null
pip install --quiet httpx psutil fastapi uvicorn pydantic 2>/dev/null
echo -e "  ${GREEN}[OK] httpx, psutil, fastapi, uvicorn, pydantic${NC}"

# ── Clone or update CH8 ──────────────────────────────────────────────────
echo -e "${BLUE}[3/4] Downloading CH8 Agent...${NC}"
INSTALL_DIR="$HOME/ch8-agent"

if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e "  ${YELLOW}Updating existing installation...${NC}"
    cd "$INSTALL_DIR"
    git fetch origin master 2>/dev/null
    git reset --hard origin/master 2>/dev/null
    cd -
else
    rm -rf "$INSTALL_DIR" 2>/dev/null
    git clone -b master https://github.com/hudsonrj/ch8-cluster-agent.git "$INSTALL_DIR"
fi

if [ ! -f "$INSTALL_DIR/ch8" ]; then
    echo -e "${RED}Clone failed. Check your internet connection.${NC}"
    exit 1
fi

chmod +x "$INSTALL_DIR/ch8"
echo -e "  ${GREEN}[OK] Installed at $INSTALL_DIR${NC}"

# ── Create symlink / PATH ────────────────────────────────────────────────
echo -e "${BLUE}[4/4] Setting up ch8 command...${NC}"

BIN_DIR="$PREFIX/bin"
ln -sf "$INSTALL_DIR/ch8" "$BIN_DIR/ch8"
echo -e "  ${GREEN}[OK] ch8 → $BIN_DIR/ch8${NC}"

# ── Optional: Termux:Boot auto-start ─────────────────────────────────────
BOOT_DIR="$HOME/.termux/boot"
mkdir -p "$BOOT_DIR"
cat > "$BOOT_DIR/ch8-start.sh" << 'BOOTSCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# Auto-start CH8 daemon on boot (requires Termux:Boot app)
export PYTHONPATH="$HOME/ch8-agent"
cd "$HOME/ch8-agent"
python3 -m connect.daemon > "$HOME/.config/ch8/daemon.log" 2>&1 &
BOOTSCRIPT
chmod +x "$BOOT_DIR/ch8-start.sh"

# ── Wake lock suggestion ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CH8 Agent installed on Android/Termux!   ${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  ${GREEN}ch8 config ai${NC}              # configure AI provider"
echo -e "  ${GREEN}ch8 up --token <TOKEN>${NC}     # join your network"
echo ""
echo -e "${YELLOW}Tips for Android:${NC}"
echo -e "  • Run ${GREEN}termux-wake-lock${NC} to keep CH8 running in background"
echo -e "  • Install ${GREEN}Termux:Boot${NC} from F-Droid for auto-start on boot"
echo -e "  • Install ${GREEN}Termux:Widget${NC} for home screen shortcuts"
echo ""
echo -e "${YELLOW}Recommended AI providers:${NC}"
echo -e "  ${GREEN}Groq${NC}   (cloud, free) — groq.com"
echo -e "  ${GREEN}OpenAI${NC} (cloud)       — openai.com"
echo -e ""
echo -e "${BLUE}Docs: https://github.com/hudsonrj/ch8-cluster-agent${NC}"
echo ""
