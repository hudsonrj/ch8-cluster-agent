#!/bin/bash
# CH8 Agent - Linux 32-bit Installation Script
# For old computers, legacy systems, i686 architecture

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
cat << "EOF"
   _____ _    _  ___
  / ____| |  | |/ _ \
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \_____|_|  |_|\___/

 Linux 32-bit Installation
EOF
echo -e "${NC}"

# Check if 32-bit
check_architecture() {
    ARCH=$(uname -m)

    if [ "$ARCH" != "i686" ] && [ "$ARCH" != "i386" ]; then
        echo -e "${YELLOW}Warning: Not detected as 32-bit (detected: $ARCH)${NC}"
        echo "Continue anyway? (y/n)"
        read -r response
        if [ "$response" != "y" ]; then
            exit 1
        fi
    fi

    echo -e "${GREEN}Architecture: $ARCH${NC}"
}

# Check RAM
check_ram() {
    RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    echo -e "${YELLOW}Available RAM: ${RAM_MB}MB${NC}"

    if [ "$RAM_MB" -lt 1024 ]; then
        echo -e "${YELLOW}Warning: Low memory detected. Minimum 1GB recommended.${NC}"
        TIER="nano"
    elif [ "$RAM_MB" -lt 2048 ]; then
        TIER="tiny"
    else
        TIER="small"
    fi

    echo -e "${GREEN}Tier: $TIER${NC}"
}

# Install dependencies
install_dependencies() {
    echo "Installing dependencies..."

    # Detect package manager
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y \
            python3 \
            python3-pip \
            python3-venv \
            git \
            curl \
            build-essential \
            cmake
    elif command -v yum &> /dev/null; then
        sudo yum install -y \
            python3 \
            python3-pip \
            git \
            curl \
            gcc \
            gcc-c++ \
            make \
            cmake
    else
        echo -e "${RED}Error: Unsupported package manager${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

# Setup swap
setup_swap() {
    if [ "$RAM_MB" -lt 2048 ]; then
        echo "Setting up swap..."

        SWAP_SIZE=$((RAM_MB * 2))
        SWAP_FILE="/swapfile"

        if [ ! -f "$SWAP_FILE" ]; then
            sudo dd if=/dev/zero of=$SWAP_FILE bs=1M count=$SWAP_SIZE status=progress
            sudo chmod 600 $SWAP_FILE
            sudo mkswap $SWAP_FILE
            sudo swapon $SWAP_FILE

            if ! grep -q "$SWAP_FILE" /etc/fstab; then
                echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab
            fi

            echo -e "${GREEN}✓ Swap configured (${SWAP_SIZE}MB)${NC}"
        fi
    fi
}

# Install llama.cpp (32-bit build)
install_llamacpp() {
    echo "Building llama.cpp for 32-bit..."

    LLAMACPP_DIR="$HOME/.ch8/llama.cpp"

    if [ ! -d "$LLAMACPP_DIR" ]; then
        git clone https://github.com/ggerganov/llama.cpp "$LLAMACPP_DIR"
        cd "$LLAMACPP_DIR"

        # Build with 32-bit flags
        CFLAGS="-m32" CXXFLAGS="-m32" make -j$(nproc)

        echo -e "${GREEN}✓ llama.cpp built for 32-bit${NC}"
    fi
}

# Download small model
download_model() {
    echo "Downloading model..."

    MODELS_DIR="$HOME/.ch8/models"
    mkdir -p "$MODELS_DIR"

    case $TIER in
        nano)
            MODEL_URL="https://huggingface.co/QuantFactory/SmolLM-135M-Instruct-GGUF/resolve/main/SmolLM-135M-Instruct.Q4_K_M.gguf"
            MODEL_NAME="smollm-135m-q4.gguf"
            ;;
        *)
            MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf"
            MODEL_NAME="tinyllama-1.1b-q2.gguf"
            ;;
    esac

    if [ ! -f "$MODELS_DIR/$MODEL_NAME" ]; then
        curl -L -o "$MODELS_DIR/$MODEL_NAME" "$MODEL_URL"
        echo -e "${GREEN}✓ Model downloaded${NC}"
    fi
}

# Install CH8 Agent
install_ch8_agent() {
    echo "Installing CH8 Agent..."

    CH8_DIR="$HOME/.ch8/ch8-agent"

    if [ ! -d "$CH8_DIR" ]; then
        git clone https://github.com/hudsonrj/ch8-cluster-agent.git "$CH8_DIR"
    else
        cd "$CH8_DIR" && git pull
    fi

    python3 -m venv "$CH8_DIR/venv"
    source "$CH8_DIR/venv/bin/activate"
    pip install --upgrade pip
    pip install aiohttp structlog psutil pyyaml
    deactivate

    echo -e "${GREEN}✓ CH8 Agent installed${NC}"
}

# Create config
create_config() {
    CONFIG_DIR="$HOME/.ch8/config"
    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_DIR/node.yaml" << EOF
node:
  id: linux32-$(hostname)
  tier: $TIER

hardware:
  platform: linux-i686
  ram_mb: $RAM_MB

llm:
  backend: llama.cpp
  model_path: $HOME/.ch8/models/$MODEL_NAME
  context_length: 512
  threads: $(nproc)

performance:
  max_concurrent_tasks: 1
  batch_processing: true
EOF

    echo -e "${GREEN}✓ Configuration created${NC}"
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   CH8 Agent Installation Complete (32-bit)!   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Architecture: 32-bit ($ARCH)"
    echo "Tier: $TIER"
    echo "RAM: ${RAM_MB}MB"
    echo ""
    echo "To start:"
    echo "  cd ~/.ch8/ch8-agent"
    echo "  source venv/bin/activate"
    echo "  python -m cluster.node"
    echo ""
}

main() {
    check_architecture
    check_ram
    install_dependencies
    setup_swap
    install_llamacpp
    download_model
    install_ch8_agent
    create_config
    print_summary
}

main
