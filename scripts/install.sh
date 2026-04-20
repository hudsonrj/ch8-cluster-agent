#!/bin/bash
# CH8 Agent - Automated Installation Script
# Usage: curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
   _____ _   _ ___    _                    _
  / ____| | | / _ \  / \   __ _  ___ _ __ | |_
 | |    | |_| | | | / _ \ / _` |/ _ \ '_ \| __|
 | |___ |  _  | |_|/ ___ \ (_| |  __/ | | | |_
  \____|_| |_|\___/_/   \_\__, |\___|_| |_|\__|
                           |___/
    Distributed Multi-Node Agent System
EOF
echo -e "${NC}"

echo -e "${GREEN}Starting CH8 Agent installation...${NC}\n"

# Check OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    echo -e "${BLUE}Detected OS: Linux${NC}"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    echo -e "${BLUE}Detected OS: macOS${NC}"
else
    echo -e "${RED}Unsupported OS: $OSTYPE${NC}"
    exit 1
fi

# Check Python version
echo -e "\n${YELLOW}Checking Python version...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 11 ]; then
        echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
    else
        echo -e "${RED}✗ Python 3.11+ required, found $PYTHON_VERSION${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Python3 not found${NC}"
    echo -e "${YELLOW}Please install Python 3.11+ first${NC}"
    exit 1
fi

# Check Redis
echo -e "\n${YELLOW}Checking Redis...${NC}"
if command -v redis-server &> /dev/null; then
    echo -e "${GREEN}✓ Redis found${NC}"
    REDIS_INSTALLED=1
else
    echo -e "${YELLOW}✗ Redis not found${NC}"
    REDIS_INSTALLED=0

    read -p "Install Redis? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ "$OS" == "linux" ]; then
            echo -e "${BLUE}Installing Redis on Linux...${NC}"
            sudo apt-get update && sudo apt-get install -y redis-server
        elif [ "$OS" == "macos" ]; then
            echo -e "${BLUE}Installing Redis on macOS...${NC}"
            brew install redis
        fi
        REDIS_INSTALLED=1
    fi
fi

# Choose installation directory
echo -e "\n${YELLOW}Installation directory:${NC}"
DEFAULT_DIR="$HOME/ch8-agent"
read -p "Enter path (default: $DEFAULT_DIR): " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_DIR}

# Create directory
echo -e "\n${BLUE}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Clone repository
echo -e "\n${BLUE}Cloning CH8 Agent repository...${NC}"
if [ -d ".git" ]; then
    echo -e "${YELLOW}Repository already exists, pulling latest changes...${NC}"
    git pull origin master
else
    git clone https://github.com/hudsonrj/ch8-cluster-agent.git .
fi

# Create virtual environment
echo -e "\n${BLUE}Creating Python virtual environment...${NC}"
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo -e "\n${BLUE}Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Configure Redis
if [ "$REDIS_INSTALLED" -eq 1 ]; then
    echo -e "\n${YELLOW}Configuring Redis...${NC}"
    read -p "Set Redis password? (recommended: 1q2w3e4r) " -r REDIS_PASSWORD
    REDIS_PASSWORD=${REDIS_PASSWORD:-1q2w3e4r}

    if [ "$OS" == "linux" ]; then
        # Linux: modify redis.conf
        echo -e "${BLUE}Setting Redis password...${NC}"
        redis-cli CONFIG SET requirepass "$REDIS_PASSWORD" 2>/dev/null || true
    elif [ "$OS" == "macos" ]; then
        # macOS: modify redis.conf
        echo -e "${BLUE}Setting Redis password...${NC}"
        redis-cli CONFIG SET requirepass "$REDIS_PASSWORD" 2>/dev/null || true
    fi
fi

# Create config files if needed
echo -e "\n${BLUE}Checking configuration files...${NC}"
if [ ! -f "config/master.yaml" ]; then
    echo -e "${YELLOW}Config files not found (this is normal for first install)${NC}"
fi

# Create helper scripts
echo -e "\n${BLUE}Creating helper scripts...${NC}"

cat > "$INSTALL_DIR/ch8-start.sh" << 'EOFSTART'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
bash test-cluster.sh
EOFSTART

cat > "$INSTALL_DIR/ch8-stop.sh" << 'EOFSTOP'
#!/bin/bash
cd "$(dirname "$0")"
bash stop-cluster.sh
EOFSTOP

cat > "$INSTALL_DIR/ch8-test.sh" << 'EOFTEST'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python test-e2e.py
EOFTEST

chmod +x ch8-start.sh ch8-stop.sh ch8-test.sh ch8

# Add to PATH (optional)
echo -e "\n${YELLOW}Add CH8 Agent to PATH?${NC}"
read -p "This will add aliases to your shell config (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SHELL_CONFIG=""
    if [ -f "$HOME/.bashrc" ]; then
        SHELL_CONFIG="$HOME/.bashrc"
    elif [ -f "$HOME/.zshrc" ]; then
        SHELL_CONFIG="$HOME/.zshrc"
    fi

    if [ -n "$SHELL_CONFIG" ]; then
        echo "" >> "$SHELL_CONFIG"
        echo "# CH8 Agent CLI and aliases" >> "$SHELL_CONFIG"
        echo "export PATH=\"\$PATH:$INSTALL_DIR\"" >> "$SHELL_CONFIG"
        echo "alias ch8-start='$INSTALL_DIR/ch8-start.sh'" >> "$SHELL_CONFIG"
        echo "alias ch8-stop='$INSTALL_DIR/ch8-stop.sh'" >> "$SHELL_CONFIG"
        echo "alias ch8-test='$INSTALL_DIR/ch8-test.sh'" >> "$SHELL_CONFIG"
        echo "alias ch8-cd='cd $INSTALL_DIR'" >> "$SHELL_CONFIG"
        echo -e "${GREEN}✓ CH8 CLI and aliases added to $SHELL_CONFIG${NC}"
        echo -e "${YELLOW}Run 'source $SHELL_CONFIG' or restart your terminal${NC}"
    fi
fi

# Installation complete
echo -e "\n${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════╗
║     CH8 Agent Installation Complete! ✓           ║
╚═══════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}Installation directory:${NC} $INSTALL_DIR"
echo -e "${BLUE}Python version:${NC} $(python3 --version)"
echo -e "${BLUE}Redis:${NC} $(redis-server --version | head -1)"

echo -e "\n${YELLOW}Quick Start Commands:${NC}"
echo -e "  ${GREEN}cd $INSTALL_DIR${NC}"
echo -e "  ${GREEN}./ch8-start.sh${NC}     - Start the cluster"
echo -e "  ${GREEN}./ch8-test.sh${NC}      - Run tests"
echo -e "  ${GREEN}./ch8-stop.sh${NC}      - Stop the cluster"

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "\n${YELLOW}Or use aliases:${NC}"
    echo -e "  ${GREEN}ch8-start${NC}          - Start the cluster"
    echo -e "  ${GREEN}ch8-test${NC}           - Run tests"
    echo -e "  ${GREEN}ch8-stop${NC}           - Stop the cluster"
    echo -e "  ${GREEN}ch8-cd${NC}             - Go to installation directory"
fi

echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "  1. Review configuration: ${BLUE}$INSTALL_DIR/config/master.yaml${NC}"
echo -e "  2. Start Redis: ${GREEN}redis-server &${NC}"
echo -e "  3. Start cluster: ${GREEN}./ch8-start.sh${NC}"
echo -e "  4. Read docs: ${BLUE}$INSTALL_DIR/README.md${NC}"

echo -e "\n${YELLOW}Documentation:${NC}"
echo -e "  ${BLUE}README.md${NC}            - Quick start guide"
echo -e "  ${BLUE}PROJECT_OVERVIEW.md${NC}  - Complete architecture"
echo -e "  ${BLUE}docs/MANUAL.md${NC}       - Detailed manual"
echo -e "  ${BLUE}TESTING.md${NC}           - Testing guide"

echo -e "\n${GREEN}Happy clustering! 🚀${NC}"
echo -e "${BLUE}GitHub: https://github.com/hudsonrj/ch8-cluster-agent${NC}\n"
