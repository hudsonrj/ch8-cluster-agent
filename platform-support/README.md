# Platform Support - Run CH8 Agent Anywhere

**Vision**: Every device, from a 20-year-old laptop to a Raspberry Pi Zero, can contribute to the distributed agent cluster.

## 🌍 Supported Platforms

### ✅ Fully Supported (Tier 1)

| Platform | Architecture | Min RAM | Min Storage | Models |
|----------|-------------|---------|-------------|--------|
| Linux x86_64 | 64-bit | 2GB | 4GB | All sizes |
| Linux ARM64 | 64-bit | 2GB | 4GB | All sizes |
| macOS Intel | x86_64 | 4GB | 8GB | All sizes |
| macOS Apple Silicon | ARM64 | 8GB | 16GB | All sizes (Metal) |
| Windows 10/11 x64 | 64-bit | 4GB | 8GB | All sizes |
| Raspberry Pi 4/5 | ARM64 | 4GB | 16GB | Small models |

### ✅ Limited Support (Tier 2)

| Platform | Architecture | Min RAM | Min Storage | Models |
|----------|-------------|---------|-------------|--------|
| Linux x86 (32-bit) | i686 | 1GB | 2GB | Tiny only |
| Windows 7/8 x86 | 32-bit | 2GB | 4GB | Tiny only |
| Raspberry Pi 3 | ARMv7 | 1GB | 8GB | Tiny only |
| Raspberry Pi Zero 2W | ARMv7 | 512MB | 4GB | Nano only |
| macOS 10.13-10.15 | x86_64 | 4GB | 8GB | Small models |

### ⚠️ Experimental (Tier 3)

| Platform | Architecture | Min RAM | Min Storage | Models |
|----------|-------------|---------|-------------|--------|
| FreeBSD | x86_64 | 2GB | 4GB | Small models |
| OpenBSD | x86_64 | 2GB | 4GB | Small models |
| Raspberry Pi 2 | ARMv7 | 512MB | 4GB | Nano only |
| Raspberry Pi Zero W | ARMv6 | 256MB | 2GB | Nano only |
| Android (Termux) | ARM64 | 2GB | 8GB | Small models |

## 📦 Model Size Categories by Hardware

### Nano Models (< 100MB)
**Hardware**: Raspberry Pi Zero, 32-bit systems with < 512MB RAM
**Models**:
- TinyStories-1M (1M params, ~2MB)
- TinyLlama-160M-3T (160M params, ~80MB)
- SmolLM-135M (135M params, ~60MB)
- Pythia-70M (70M params, ~35MB)

**Use Cases**:
- Simple text classification
- Basic entity extraction
- Yes/no questions
- Keyword matching
- Simple transformations

### Tiny Models (100-500MB)
**Hardware**: Raspberry Pi 2/3, 32-bit with 512MB-1GB RAM
**Models**:
- Phi-2-mini Q2_K (400MB)
- TinyLlama-1.1B Q2_K (450MB)
- Qwen2-0.5B Q2_K (300MB)
- SmolLM-360M (180MB)

**Use Cases**:
- Text summarization
- Simple reasoning
- Code snippets
- Basic Q&A
- Data extraction

### Small Models (500MB-2GB)
**Hardware**: Raspberry Pi 4, old laptops, 32-bit with 2GB RAM
**Models**:
- Phi-3-mini Q4_K_M (1.8GB)
- TinyLlama-1.1B Q4_K_M (700MB)
- Qwen2-0.5B Q4_K_M (500MB)
- Gemma-2B Q4_K_S (1.3GB)

**Use Cases**:
- Code generation
- Analysis
- Creative writing
- Complex reasoning
- General chat

### Medium Models (2-8GB)
**Hardware**: Modern systems, 4GB+ RAM
**Models**:
- Llama-3-8B Q4_K_M (4.5GB)
- Mistral-7B Q4_K_M (4GB)
- Gemma-7B Q4_K_M (4GB)

**Use Cases**:
- Result aggregation
- Quality synthesis
- Complex tasks
- Production workloads

## 🎯 Auto-Detection System

The CH8 Agent automatically detects hardware capabilities and selects appropriate models:

```python
# Auto-detection on startup
system_info = {
    'platform': 'linux',
    'arch': 'armv7l',
    'ram_mb': 1024,
    'storage_gb': 8,
    'has_gpu': False
}

# Automatically selects appropriate tier
selected_tier = 'tiny'  # For Raspberry Pi 3
recommended_models = ['tinyllama-1.1b-q2_k', 'qwen2-0.5b-q2_k']
```

## 🚀 Installation by Platform

### Linux x86_64 (Modern)
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash
```

### Linux x86 (32-bit)
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-32bit.sh | bash
```

### Raspberry Pi (All Models)
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-rpi.sh | bash
```

### Windows x64
```powershell
powershell -c "iwr -useb https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.ps1 | iex"
```

### Windows x86 (32-bit)
```powershell
powershell -c "iwr -useb https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-win32.ps1 | iex"
```

### macOS (Intel/Apple Silicon)
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-macos.sh | bash
```

### macOS (Old versions 10.13-10.15)
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-macos-legacy.sh | bash
```

## 🔧 Hardware-Specific Optimizations

### Raspberry Pi Optimization
- Use Q2_K quantization (2-bit)
- Enable swap if < 1GB RAM
- CPU affinity for better performance
- Reduce context length to 512-1024

### 32-bit Systems
- Use 32-bit Python builds
- Limit max model size to RAM/2
- Disable embeddings (save memory)
- Single model per node

### Old Mac (Pre-2015)
- Use CPU-only llama.cpp
- Avoid Metal acceleration
- Limit concurrent operations
- Use Q4_K_S quantization

### Android (Termux)
- Install via Termux
- Use Proot for better compatibility
- Limit background processing
- Use battery-efficient models

## 📊 Performance by Platform

### Raspberry Pi 4 (4GB RAM)
```
Model: TinyLlama-1.1B Q4_K_M
Tokens/sec: ~8-12
Latency: ~100-150ms per token
Suitable for: Real-time chat, data extraction
```

### Raspberry Pi 3 (1GB RAM)
```
Model: TinyLlama-1.1B Q2_K
Tokens/sec: ~3-5
Latency: ~200-300ms per token
Suitable for: Background tasks, batch processing
```

### Raspberry Pi Zero 2W (512MB RAM)
```
Model: SmolLM-135M
Tokens/sec: ~1-2
Latency: ~500-1000ms per token
Suitable for: Simple classification, extraction
```

### Linux 32-bit (2GB RAM)
```
Model: Qwen2-0.5B Q4_K_M
Tokens/sec: ~5-8
Latency: ~150-200ms per token
Suitable for: General tasks, small workloads
```

## 🎮 Cluster Topology Examples

### Mixed Hardware Cluster

```
┌─────────────────────────────────────────┐
│         CH8 Agent Cluster               │
├─────────────────────────────────────────┤
│                                         │
│ Node 1: Server (Linux x86_64, 32GB)    │
│ └─ Llama-3-8B Q4_K_M (aggregation)     │
│                                         │
│ Node 2: Laptop (macOS Intel, 8GB)      │
│ └─ Mistral-7B Q4_K_M (synthesis)       │
│                                         │
│ Node 3: Desktop (Windows 10, 16GB)     │
│ └─ Gemma-7B Q4_K_M (analysis)          │
│                                         │
│ Node 4: Raspberry Pi 4 (4GB)           │
│ └─ TinyLlama-1.1B Q4_K_M (extraction)  │
│                                         │
│ Node 5: Raspberry Pi 3 (1GB)           │
│ └─ Qwen2-0.5B Q2_K (classification)    │
│                                         │
│ Node 6: Old Laptop (Linux 32-bit, 2GB) │
│ └─ SmolLM-360M (simple tasks)          │
│                                         │
│ Node 7: Pi Zero 2W (512MB)             │
│ └─ SmolLM-135M (keywords)              │
│                                         │
└─────────────────────────────────────────┘

Total Capacity: 7 nodes, all contributing!
```

## 💡 Optimization Strategies

### Memory-Constrained Devices
```python
config = {
    'model_size': 'nano',
    'context_length': 512,
    'batch_size': 1,
    'swap_enabled': True,
    'cache_size': 0,  # Disable KV cache
    'threads': 1
}
```

### CPU-Only Devices
```python
config = {
    'backend': 'llama.cpp',
    'quantization': 'Q4_K_M',
    'threads': 'auto',  # Use all available
    'mlock': False,  # Don't lock memory
    'mmap': True   # Memory-mapped model
}
```

### Battery-Powered Devices
```python
config = {
    'power_mode': 'efficient',
    'cpu_limit': 50,  # 50% CPU max
    'sleep_between_tasks': True,
    'batch_tasks': True  # Wait for batches
}
```

## 🔍 Hardware Detection

```python
from platform_support import detect_hardware

info = detect_hardware()
# {
#     'platform': 'linux',
#     'architecture': 'armv7l',
#     'cpu_cores': 4,
#     'ram_mb': 1024,
#     'ram_available_mb': 512,
#     'storage_gb': 16,
#     'has_gpu': False,
#     'is_raspberry_pi': True,
#     'pi_model': '3B',
#     'tier': 'tiny',
#     'recommended_models': ['tinyllama-1.1b-q2_k'],
#     'max_model_size_mb': 500
# }
```

## 📱 Mobile/Edge Support

### Raspberry Pi Cluster
Perfect for edge computing clusters:
- Low power consumption
- Small form factor
- Easy to deploy
- Can run 24/7

### Android via Termux
Run on Android phones/tablets:
```bash
pkg install python git
pip install ch8-agent
ch8 start --mobile-mode
```

### IoT Devices
Ultra-lightweight mode for IoT:
- Nano models only
- Event-driven processing
- Minimal memory footprint
- MQTT integration

## 🎯 Best Practices

### For Old Hardware
1. Use maximum quantization (Q2_K)
2. Reduce context length to minimum
3. Enable swap space
4. Single model per machine
5. Batch processing instead of real-time

### For Raspberry Pi
1. Use active cooling
2. Overclock if stable
3. Use SD card for storage only
4. Add swap on USB drive
5. Monitor temperature

### For 32-bit Systems
1. Use 32-bit Python
2. Avoid large models
3. Clear cache frequently
4. Monitor memory usage
5. Use lightweight backends

### For Battery Devices
1. Set CPU limits
2. Use power-efficient models
3. Batch operations
4. Sleep between tasks
5. Monitor battery drain

## 🚦 Status Monitoring

Each node reports its capabilities:

```json
{
  "node_id": "rpi3-living-room",
  "platform": "linux-armv7l",
  "tier": "tiny",
  "status": "active",
  "model": "qwen2-0.5b-q2_k",
  "load": {
    "cpu": 45,
    "ram": 78,
    "swap": 23
  },
  "performance": {
    "tokens_per_sec": 4.2,
    "tasks_completed": 147
  },
  "health": "good"
}
```

## 🎁 Benefits

✅ **Democratic AI**: Anyone can participate
✅ **Utilize Old Hardware**: Give new life to old devices
✅ **Energy Efficient**: Small models use less power
✅ **Distributed Load**: Many small nodes = robust system
✅ **Accessible**: No expensive hardware needed
✅ **Scalable**: Add any device to cluster
✅ **Resilient**: Losing one node doesn't hurt

## 📚 Platform-Specific Docs

- [Linux 32-bit Guide](linux-32bit.md)
- [Raspberry Pi Guide](raspberry-pi.md)
- [Windows 32-bit Guide](windows-32bit.md)
- [Old macOS Guide](macos-legacy.md)
- [Android/Termux Guide](android-termux.md)
- [FreeBSD Guide](freebsd.md)

## 🎖️ Success Stories

**Home Lab Cluster**:
- 1x Old Dell laptop (Linux 32-bit, 2GB) - Coordinator
- 3x Raspberry Pi 3 (1GB each) - Workers
- 1x Raspberry Pi Zero 2W (512MB) - Simple tasks
- Total cost: < $150, runs 24/7, handles real workloads

**School Computer Lab**:
- 20x Old PCs (Windows 7 32-bit, 2GB each)
- Runs during off-hours
- Processes student data analysis
- Zero additional hardware cost

**Maker Space**:
- Mixed: Macs, PCs, Raspberry Pis
- All contribute to shared cluster
- Handles various AI tasks
- Community-powered AI

---

**Remember**: In CH8 Agent, every machine matters. From the latest GPU server to a 10-year-old laptop, all can contribute to the distributed intelligence! 🚀
