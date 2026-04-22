#!/data/data/com.termux/files/usr/bin/bash
# CH8 Agent - Android/Termux Installation Script

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}"
cat << "EOF"
   _____ _    _  ___
  / ____| |  | |/ _ \
 | |    | |__| | (_) |
 | |    |  __  |> _ <
 | |____| |  | | (_) |
  \_____|_|  |_|\___/

 Android/Termux Installation
EOF
echo -e "${NC}"

# Check if running in Termux
if [ ! -d "/data/data/com.termux" ]; then
    echo -e "${RED}Error: Not running in Termux${NC}"
    echo "Please install Termux from F-Droid:"
    echo "https://f-droid.org/en/packages/com.termux/"
    exit 1
fi

echo -e "${GREEN}✓ Detected Termux environment${NC}"

# Detect device info
detect_device() {
    RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    CPU_CORES=$(nproc)
    ANDROID_VER=$(getprop ro.build.version.release)

    echo -e "${YELLOW}Device Info:${NC}"
    echo "  RAM: ${RAM_MB}MB"
    echo "  CPU Cores: $CPU_CORES"
    echo "  Android: $ANDROID_VER"

    # Determine tier
    if [ "$RAM_MB" -lt 2048 ]; then
        TIER="nano"
        MODE="cloud"  # Force cloud for low RAM
        echo -e "${YELLOW}  Tier: NANO (Cloud mode recommended)${NC}"
    elif [ "$RAM_MB" -lt 4096 ]; then
        TIER="tiny"
        MODE="hybrid"
        echo -e "${YELLOW}  Tier: TINY (Hybrid mode)${NC}"
    else
        TIER="small"
        MODE="local"
        echo -e "${GREEN}  Tier: SMALL (Local capable)${NC}"
    fi
}

# Install dependencies
install_dependencies() {
    echo "Installing dependencies..."

    pkg update -y
    pkg install -y \
        python \
        git \
        clang \
        cmake \
        wget \
        proot \
        termux-api

    pip install --upgrade pip
    pip install \
        aiohttp \
        structlog \
        psutil \
        pyyaml \
        requests

    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

# Setup storage access
setup_storage() {
    if [ ! -d ~/storage ]; then
        echo "Setting up storage access..."
        termux-setup-storage
        sleep 2
        echo -e "${GREEN}✓ Storage access granted${NC}"
    fi
}

# Install llama.cpp for local models (optional)
install_llamacpp() {
    if [ "$MODE" = "local" ] || [ "$MODE" = "hybrid" ]; then
        echo "Installing llama.cpp for local models..."

        LLAMACPP_DIR="$HOME/.ch8/llama.cpp"

        if [ ! -d "$LLAMACPP_DIR" ]; then
            git clone https://github.com/ggerganov/llama.cpp "$LLAMACPP_DIR"
            cd "$LLAMACPP_DIR"

            # Build for ARM
            make -j$CPU_CORES

            echo -e "${GREEN}✓ llama.cpp compiled${NC}"
        fi
    fi
}

# Download model
download_model() {
    if [ "$MODE" = "local" ] || [ "$MODE" = "hybrid" ]; then
        echo "Downloading model..."

        MODELS_DIR="$HOME/.ch8/models"
        mkdir -p "$MODELS_DIR"

        case $TIER in
            nano|tiny)
                MODEL_URL="https://huggingface.co/QuantFactory/SmolLM-135M-Instruct-GGUF/resolve/main/SmolLM-135M-Instruct.Q4_K_M.gguf"
                MODEL_NAME="smollm-135m-q4.gguf"
                ;;
            small)
                MODEL_URL="https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q2_K.gguf"
                MODEL_NAME="tinyllama-1.1b-q2.gguf"
                ;;
        esac

        if [ ! -f "$MODELS_DIR/$MODEL_NAME" ]; then
            wget -O "$MODELS_DIR/$MODEL_NAME" "$MODEL_URL"
            echo -e "${GREEN}✓ Model downloaded${NC}"
        fi
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

    # Install Python dependencies (minimal for Android)
    cd "$CH8_DIR"
    pip install -r android/requirements.txt

    echo -e "${GREEN}✓ CH8 Agent installed${NC}"
}

# Create configuration
create_config() {
    CONFIG_DIR="$HOME/.ch8/config"
    mkdir -p "$CONFIG_DIR"

    cat > "$CONFIG_DIR/android-node.yaml" << EOF
# CH8 Agent Android Configuration
mode: $MODE

node:
  id: android-$HOSTNAME
  platform: android-termux
  tier: $TIER

hardware:
  ram_mb: $RAM_MB
  cpu_cores: $CPU_CORES
  android_version: $ANDROID_VER

battery:
  optimization: true
  power_mode: efficient
  max_cpu_usage: 50
  temperature_limit: 40
  pause_when_battery_low: true
  min_battery_level: 20

EOF

    if [ "$MODE" = "local" ] || [ "$MODE" = "hybrid" ]; then
        cat >> "$CONFIG_DIR/android-node.yaml" << EOF
local:
  backend: llama.cpp
  model_path: $HOME/.ch8/models/$MODEL_NAME
  context_length: 512
  threads: $CPU_CORES

EOF
    fi

    if [ "$MODE" = "cloud" ] || [ "$MODE" = "hybrid" ]; then
        cat >> "$CONFIG_DIR/android-node.yaml" << EOF
cloud:
  provider: groq  # Free, fast
  api_key: YOUR_API_KEY_HERE
  model: llama3-8b-8192

  # Or use OpenAI
  # provider: openai
  # api_key: sk-...
  # model: gpt-3.5-turbo

EOF
    fi

    cat >> "$CONFIG_DIR/android-node.yaml" << EOF
cluster:
  discovery_enabled: true
  coordinator_url: null  # Auto-discover

performance:
  max_concurrent_tasks: 1
  batch_processing: true
  wifi_only: true  # Only use cloud on WiFi
EOF

    echo -e "${GREEN}✓ Configuration created${NC}"
}

# Create helper scripts
create_scripts() {
    # Start script
    cat > "$HOME/.ch8/ch8-android" << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash

case "$1" in
    start)
        echo "Starting CH8 Agent Android Node..."
        cd ~/.ch8/ch8-agent
        python -m android.node &
        echo $! > ~/.ch8/node.pid
        echo "✓ Node started (PID: $(cat ~/.ch8/node.pid))"
        ;;
    stop)
        if [ -f ~/.ch8/node.pid ]; then
            kill $(cat ~/.ch8/node.pid)
            rm ~/.ch8/node.pid
            echo "✓ Node stopped"
        else
            echo "Node not running"
        fi
        ;;
    status)
        if [ -f ~/.ch8/node.pid ] && kill -0 $(cat ~/.ch8/node.pid) 2>/dev/null; then
            echo "✓ Node running (PID: $(cat ~/.ch8/node.pid))"
        else
            echo "✗ Node not running"
        fi
        ;;
    logs)
        tail -f ~/.ch8/logs/android-node.log
        ;;
    config)
        nano ~/.ch8/config/android-node.yaml
        ;;
    *)
        echo "Usage: ch8-android {start|stop|status|logs|config}"
        ;;
esac
EOF

    chmod +x "$HOME/.ch8/ch8-android"

    # Add to PATH
    if ! grep -q 'ch8-android' ~/.bashrc; then
        echo 'export PATH="$HOME/.ch8:$PATH"' >> ~/.bashrc
    fi

    echo -e "${GREEN}✓ Helper scripts created${NC}"
}

# Print summary
print_summary() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   CH8 Agent Android Installation Complete!    ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Device: Android $ANDROID_VER"
    echo "Tier: $TIER"
    echo "Mode: $MODE"
    echo "RAM: ${RAM_MB}MB"
    echo ""
    echo "Commands:"
    echo "  Start node:  ch8-android start"
    echo "  Stop node:   ch8-android stop"
    echo "  Status:      ch8-android status"
    echo "  View logs:   ch8-android logs"
    echo "  Edit config: ch8-android config"
    echo ""

    if [ "$MODE" = "cloud" ] || [ "$MODE" = "hybrid" ]; then
        echo -e "${YELLOW}⚠ Important: Configure your cloud API key:${NC}"
        echo "  ch8-android config"
        echo "  (Set your Groq/OpenAI API key)"
        echo ""
    fi

    echo "To start now:"
    echo "  source ~/.bashrc"
    echo "  ch8-android start"
    echo ""
}

# Main installation
main() {
    detect_device
    install_dependencies
    setup_storage
    install_llamacpp
    download_model
    install_ch8_agent
    create_config
    create_scripts
    print_summary
}

main
