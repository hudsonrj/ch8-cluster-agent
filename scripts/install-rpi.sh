#!/bin/bash
# CH8 Agent - Raspberry Pi Installation Script
# Supports: Pi Zero, Pi 2, Pi 3, Pi 4, Pi 5

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
cat << "EOF"
   _____ _    _  ___
  / ____| |  | |/ _ \
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \_____|_|  |_|\___/

 Raspberry Pi Installation
EOF
echo -e "${NC}"

# Detect Raspberry Pi model
detect_pi_model() {
    if [ ! -f /proc/device-tree/model ]; then
        echo -e "${RED}Error: Not running on Raspberry Pi${NC}"
        exit 1
    fi

    PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
    echo -e "${GREEN}Detected: $PI_MODEL${NC}"

    # Determine tier
    if echo "$PI_MODEL" | grep -q "Zero 2"; then
        TIER="tiny"
        RAM_MB=512
    elif echo "$PI_MODEL" | grep -q "Zero"; then
        TIER="nano"
        RAM_MB=256
    elif echo "$PI_MODEL" | grep -q "Pi 2"; then
        TIER="tiny"
        RAM_MB=1024
    elif echo "$PI_MODEL" | grep -q "Pi 3"; then
        TIER="tiny"
        RAM_MB=1024
    elif echo "$PI_MODEL" | grep -q "Pi 4"; then
        TIER="small"
        RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    elif echo "$PI_MODEL" | grep -q "Pi 5"; then
        TIER="small"
        RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    else
        TIER="tiny"
        RAM_MB=1024
    fi

    echo -e "${YELLOW}Hardware Tier: $TIER (${RAM_MB}MB RAM)${NC}"
}

# Check system requirements
check_requirements() {
    echo "Checking system requirements..."

    # Check available space
    AVAILABLE_SPACE=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$AVAILABLE_SPACE" -lt 2 ]; then
        echo -e "${RED}Error: Insufficient storage. Need at least 2GB free.${NC}"
        exit 1
    fi

    # Check if running as non-root
    if [ "$EUID" -eq 0 ]; then
        echo -e "${YELLOW}Warning: Running as root. Recommended to run as regular user.${NC}"
    fi

    echo -e "${GREEN}✓ System requirements met${NC}"
}

# Install system dependencies
install_dependencies() {
    echo "Installing dependencies..."

    sudo apt-get update
    sudo apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        git \
        curl \
        build-essential \
        cmake

    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

# Setup swap for low-memory devices
setup_swap() {
    if [ "$RAM_MB" -lt 2048 ]; then
        echo "Setting up swap for low-memory device..."

        SWAP_SIZE=$((RAM_MB * 2))
        SWAP_FILE="/swapfile"

        if [ ! -f "$SWAP_FILE" ]; then
            sudo dd if=/dev/zero of=$SWAP_FILE bs=1M count=$SWAP_SIZE status=progress
            sudo chmod 600 $SWAP_FILE
            sudo mkswap $SWAP_FILE
            sudo swapon $SWAP_FILE

            # Make permanent
            if ! grep -q "$SWAP_FILE" /etc/fstab; then
                echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab
            fi

            echo -e "${GREEN}✓ Swap configured (${SWAP_SIZE}MB)${NC}"
        else
            echo -e "${YELLOW}Swap already configured${NC}"
        fi
    fi
}

# Install llama.cpp (best for ARM)
install_llamacpp() {
    echo "Installing llama.cpp..."

    LLAMACPP_DIR="$HOME/.ch8/llama.cpp"

    if [ ! -d "$LLAMACPP_DIR" ]; then
        git clone https://github.com/ggerganov/llama.cpp "$LLAMACPP_DIR"
        cd "$LLAMACPP_DIR"

        # Build with optimizations for ARM
        if echo "$PI_MODEL" | grep -q "Pi 4\|Pi 5"; then
            # Pi 4/5 have NEON
            make LLAMA_NO_ACCELERATE=1 -j4
        else
            # Older Pi models
            make LLAMA_NO_ACCELERATE=1 -j2
        fi

        echo -e "${GREEN}✓ llama.cpp installed${NC}"
    else
        echo -e "${YELLOW}llama.cpp already installed${NC}"
    fi
}

# Download appropriate model
download_model() {
    echo "Downloading model for $TIER tier..."

    MODELS_DIR="$HOME/.ch8/models"
    mkdir -p "$MODELS_DIR"

    case $TIER in
        nano)
            MODEL_URL="https://huggingface.co/QuantFactory/SmolLM-135M-Instruct-GGUF/resolve/main/SmolLM-135M-Instruct.Q4_K_M.gguf"
            MODEL_NAME="smollm-135m-q4.gguf"
            ;;
        tiny)
            MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf"
            MODEL_NAME="tinyllama-1.1b-q2.gguf"
            ;;
        small)
            MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
            MODEL_NAME="tinyllama-1.1b-q4.gguf"
            ;;
    esac

    if [ ! -f "$MODELS_DIR/$MODEL_NAME" ]; then
        echo "Downloading $MODEL_NAME..."
        curl -L -o "$MODELS_DIR/$MODEL_NAME" "$MODEL_URL"
        echo -e "${GREEN}✓ Model downloaded${NC}"
    else
        echo -e "${YELLOW}Model already downloaded${NC}"
    fi
}

# Install CH8 Agent
install_ch8_agent() {
    echo "Installing CH8 Agent..."

    CH8_DIR="$HOME/.ch8/ch8-agent"

    if [ ! -d "$CH8_DIR" ]; then
        git clone https://github.com/hudsonrj/ch8-cluster-agent.git "$CH8_DIR"
    else
        echo "Updating CH8 Agent..."
        cd "$CH8_DIR"
        git pull
    fi

    # Create virtual environment
    python3 -m venv "$CH8_DIR/venv"
    source "$CH8_DIR/venv/bin/activate"

    # Install Python dependencies (minimal for Pi)
    pip install --upgrade pip
    pip install \
        aiohttp \
        structlog \
        psutil \
        pyyaml

    deactivate

    echo -e "${GREEN}✓ CH8 Agent installed${NC}"
}

# Create configuration
create_config() {
    echo "Creating configuration..."

    CONFIG_DIR="$HOME/.ch8/config"
    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_DIR/node.yaml" << EOF
# CH8 Agent Configuration for Raspberry Pi
node:
  id: rpi-$(hostname)
  tier: $TIER

hardware:
  platform: linux-arm
  ram_mb: $RAM_MB
  model: $PI_MODEL

llm:
  backend: llama.cpp
  model_path: $HOME/.ch8/models/$MODEL_NAME
  context_length: 512
  threads: $(nproc)

cluster:
  discovery_enabled: true
  coordinator_url: null  # Auto-discover

performance:
  max_concurrent_tasks: 1
  batch_processing: true
  power_efficient: true
EOF

    echo -e "${GREEN}✓ Configuration created${NC}"
}

# Create systemd service
create_service() {
    echo "Creating systemd service..."

    SERVICE_FILE="/etc/systemd/system/ch8-agent.service"

    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=CH8 Agent - Distributed AI Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/.ch8/ch8-agent
ExecStart=$HOME/.ch8/ch8-agent/venv/bin/python -m cluster.node
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable ch8-agent

    echo -e "${GREEN}✓ Systemd service created${NC}"
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     CH8 Agent Installation Complete!          ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Hardware: $PI_MODEL"
    echo "Tier: $TIER"
    echo "RAM: ${RAM_MB}MB"
    echo ""
    echo "Commands:"
    echo "  Start agent:  sudo systemctl start ch8-agent"
    echo "  Stop agent:   sudo systemctl stop ch8-agent"
    echo "  Status:       sudo systemctl status ch8-agent"
    echo "  Logs:         journalctl -u ch8-agent -f"
    echo ""
    echo "Or run manually:"
    echo "  cd ~/.ch8/ch8-agent"
    echo "  source venv/bin/activate"
    echo "  python -m cluster.node"
    echo ""
    echo -e "${YELLOW}Note: First startup may take a few minutes${NC}"
    echo -e "${YELLOW}      to load the model into memory.${NC}"
    echo ""
}

# Main installation flow
main() {
    detect_pi_model
    check_requirements
    install_dependencies
    setup_swap
    install_llamacpp
    download_model
    install_ch8_agent
    create_config
    create_service
    print_summary
}

# Run installation
main
