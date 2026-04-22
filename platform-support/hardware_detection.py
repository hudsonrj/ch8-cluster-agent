"""
Hardware Detection and Capability Assessment

Automatically detects hardware capabilities and recommends
appropriate models and configurations for CH8 Agent.
"""

import platform
import os
import subprocess
import psutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class HardwareTier(Enum):
    """Hardware capability tiers"""
    NANO = "nano"      # < 512MB RAM, Pi Zero, very old systems
    TINY = "tiny"      # 512MB-2GB RAM, Pi 2/3, 32-bit systems
    SMALL = "small"    # 2-8GB RAM, Pi 4, old laptops
    MEDIUM = "medium"  # 8-16GB RAM, modern PCs
    LARGE = "large"    # 16GB+ RAM, workstations
    XLARGE = "xlarge"  # 32GB+ RAM, servers


@dataclass
class ModelRecommendation:
    """Model recommendation based on hardware"""
    name: str
    size_mb: int
    quantization: str
    backend: str
    use_case: str


@dataclass
class HardwareInfo:
    """Complete hardware information"""
    # Platform
    platform: str
    architecture: str
    is_64bit: bool
    os_version: str

    # CPU
    cpu_model: str
    cpu_cores: int
    cpu_threads: int
    cpu_freq_mhz: float

    # Memory
    ram_total_mb: int
    ram_available_mb: int
    swap_total_mb: int

    # Storage
    storage_total_gb: float
    storage_available_gb: float

    # GPU
    has_gpu: bool
    gpu_type: Optional[str]
    gpu_vram_mb: Optional[int]

    # Special hardware
    is_raspberry_pi: bool
    pi_model: Optional[str]
    has_metal: bool  # Apple Silicon
    has_cuda: bool   # NVIDIA GPU

    # Tier
    tier: HardwareTier

    # Recommendations
    recommended_models: List[ModelRecommendation]
    max_model_size_mb: int
    optimal_backend: str


class HardwareDetector:
    """Detect hardware capabilities"""

    @staticmethod
    def detect() -> HardwareInfo:
        """Detect all hardware information"""
        # Platform detection
        platform_name = platform.system().lower()
        architecture = platform.machine().lower()
        is_64bit = platform.architecture()[0] == '64bit'
        os_version = platform.release()

        # CPU detection
        cpu_model = HardwareDetector._get_cpu_model()
        cpu_info = psutil.cpu_count(logical=False), psutil.cpu_count(logical=True)
        cpu_cores, cpu_threads = cpu_info if cpu_info[0] else (1, 1)

        try:
            cpu_freq = psutil.cpu_freq()
            cpu_freq_mhz = cpu_freq.current if cpu_freq else 0
        except:
            cpu_freq_mhz = 0

        # Memory detection
        mem = psutil.virtual_memory()
        ram_total_mb = mem.total // (1024 * 1024)
        ram_available_mb = mem.available // (1024 * 1024)

        swap = psutil.swap_memory()
        swap_total_mb = swap.total // (1024 * 1024)

        # Storage detection
        disk = psutil.disk_usage('/')
        storage_total_gb = disk.total / (1024**3)
        storage_available_gb = disk.free / (1024**3)

        # GPU detection
        has_gpu, gpu_type, gpu_vram_mb = HardwareDetector._detect_gpu()

        # Special hardware detection
        is_raspberry_pi, pi_model = HardwareDetector._detect_raspberry_pi()
        has_metal = HardwareDetector._detect_metal()
        has_cuda = HardwareDetector._detect_cuda()

        # Determine tier
        tier = HardwareDetector._determine_tier(
            ram_total_mb, cpu_cores, has_gpu, is_raspberry_pi
        )

        # Get recommendations
        recommended_models = HardwareDetector._get_model_recommendations(tier, architecture, has_gpu)
        max_model_size_mb = HardwareDetector._calculate_max_model_size(ram_total_mb, tier)
        optimal_backend = HardwareDetector._determine_optimal_backend(
            platform_name, architecture, has_gpu, has_metal, has_cuda
        )

        return HardwareInfo(
            platform=platform_name,
            architecture=architecture,
            is_64bit=is_64bit,
            os_version=os_version,
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            cpu_freq_mhz=cpu_freq_mhz,
            ram_total_mb=ram_total_mb,
            ram_available_mb=ram_available_mb,
            swap_total_mb=swap_total_mb,
            storage_total_gb=storage_total_gb,
            storage_available_gb=storage_available_gb,
            has_gpu=has_gpu,
            gpu_type=gpu_type,
            gpu_vram_mb=gpu_vram_mb,
            is_raspberry_pi=is_raspberry_pi,
            pi_model=pi_model,
            has_metal=has_metal,
            has_cuda=has_cuda,
            tier=tier,
            recommended_models=recommended_models,
            max_model_size_mb=max_model_size_mb,
            optimal_backend=optimal_backend
        )

    @staticmethod
    def _get_cpu_model() -> str:
        """Get CPU model name"""
        try:
            if platform.system() == 'Linux':
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line:
                            return line.split(':')[1].strip()
                        elif 'Model' in line:  # ARM CPUs
                            return line.split(':')[1].strip()
            elif platform.system() == 'Darwin':
                result = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'])
                return result.decode().strip()
            elif platform.system() == 'Windows':
                result = subprocess.check_output(['wmic', 'cpu', 'get', 'name'])
                return result.decode().split('\n')[1].strip()
        except:
            pass

        return platform.processor() or 'Unknown'

    @staticmethod
    def _detect_gpu() -> tuple[bool, Optional[str], Optional[int]]:
        """Detect GPU presence and type"""
        try:
            # Try NVIDIA
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                   capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                gpu_info = result.stdout.strip().split(',')
                gpu_name = gpu_info[0].strip()
                gpu_vram = int(gpu_info[1].strip().split()[0])
                return True, f"NVIDIA {gpu_name}", gpu_vram
        except:
            pass

        try:
            # Try AMD
            result = subprocess.run(['rocm-smi', '--showproductname'],
                                   capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and 'GPU' in result.stdout:
                return True, "AMD GPU", None
        except:
            pass

        # Check for integrated GPU (Intel/AMD)
        if platform.system() == 'Linux':
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    content = f.read()
                    if 'Intel' in content or 'AMD' in content:
                        return True, "Integrated GPU", None
            except:
                pass

        return False, None, None

    @staticmethod
    def _detect_raspberry_pi() -> tuple[bool, Optional[str]]:
        """Detect if running on Raspberry Pi"""
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
                if 'Raspberry Pi' in content or 'BCM' in content:
                    # Try to get model
                    try:
                        with open('/proc/device-tree/model', 'r') as m:
                            model = m.read().strip().replace('\x00', '')
                            if 'Zero' in model:
                                if 'Zero 2' in model:
                                    return True, 'Zero 2W'
                                return True, 'Zero W'
                            elif 'Pi 2' in model:
                                return True, '2'
                            elif 'Pi 3' in model:
                                return True, '3'
                            elif 'Pi 4' in model:
                                return True, '4'
                            elif 'Pi 5' in model:
                                return True, '5'
                            return True, 'Unknown'
                    except:
                        return True, 'Unknown'
        except:
            pass

        return False, None

    @staticmethod
    def _detect_metal() -> bool:
        """Detect Apple Metal support (M1/M2/M3)"""
        if platform.system() != 'Darwin':
            return False

        try:
            result = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'])
            cpu = result.decode().strip()
            return 'Apple' in cpu and ('M1' in cpu or 'M2' in cpu or 'M3' in cpu)
        except:
            return False

    @staticmethod
    def _detect_cuda() -> bool:
        """Detect CUDA support"""
        try:
            result = subprocess.run(['nvidia-smi'], capture_output=True, timeout=2)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def _determine_tier(ram_mb: int, cpu_cores: int, has_gpu: bool, is_rpi: bool) -> HardwareTier:
        """Determine hardware tier"""
        # Raspberry Pi specific tiers
        if is_rpi:
            if ram_mb <= 512:
                return HardwareTier.NANO
            elif ram_mb <= 2048:
                return HardwareTier.TINY
            else:
                return HardwareTier.SMALL

        # General tiers
        if ram_mb < 512:
            return HardwareTier.NANO
        elif ram_mb < 2048:
            return HardwareTier.TINY
        elif ram_mb < 8192:
            return HardwareTier.SMALL
        elif ram_mb < 16384:
            return HardwareTier.MEDIUM
        elif ram_mb < 32768:
            return HardwareTier.LARGE
        else:
            return HardwareTier.XLARGE

    @staticmethod
    def _get_model_recommendations(tier: HardwareTier, arch: str, has_gpu: bool) -> List[ModelRecommendation]:
        """Get model recommendations based on tier"""
        recommendations = {
            HardwareTier.NANO: [
                ModelRecommendation("SmolLM-135M", 60, "Q4_K_M", "llama.cpp", "classification"),
                ModelRecommendation("TinyStories-1M", 2, "Q8_0", "llama.cpp", "simple_generation"),
            ],
            HardwareTier.TINY: [
                ModelRecommendation("Qwen2-0.5B", 300, "Q2_K", "llama.cpp", "general"),
                ModelRecommendation("TinyLlama-1.1B", 450, "Q2_K", "llama.cpp", "chat"),
                ModelRecommendation("SmolLM-360M", 180, "Q4_K_M", "llama.cpp", "analysis"),
            ],
            HardwareTier.SMALL: [
                ModelRecommendation("Phi-3-mini", 1800, "Q4_K_M", "llama.cpp", "reasoning"),
                ModelRecommendation("TinyLlama-1.1B", 700, "Q4_K_M", "llama.cpp", "general"),
                ModelRecommendation("Qwen2-0.5B", 500, "Q4_K_M", "llama.cpp", "fast"),
                ModelRecommendation("Gemma-2B", 1300, "Q4_K_S", "llama.cpp", "aggregation"),
            ],
            HardwareTier.MEDIUM: [
                ModelRecommendation("Phi-3-mini", 2200, "Q5_K_M", "llama.cpp", "reasoning"),
                ModelRecommendation("Gemma-2B", 1600, "Q5_K_M", "llama.cpp", "general"),
                ModelRecommendation("Mistral-7B", 4000, "Q4_K_M", "llama.cpp" if not has_gpu else "vllm", "synthesis"),
            ],
            HardwareTier.LARGE: [
                ModelRecommendation("Llama-3-8B", 4500, "Q4_K_M", "vllm" if has_gpu else "llama.cpp", "general"),
                ModelRecommendation("Mistral-7B", 4000, "Q5_K_M", "vllm" if has_gpu else "llama.cpp", "aggregation"),
                ModelRecommendation("Gemma-7B", 4000, "Q5_K_M", "llama.cpp", "synthesis"),
            ],
            HardwareTier.XLARGE: [
                ModelRecommendation("Llama-3-70B", 40000, "Q4_K_M", "vllm", "production"),
                ModelRecommendation("Mixtral-8x7B", 25000, "Q4_K_M", "vllm", "moe"),
            ]
        }

        return recommendations.get(tier, recommendations[HardwareTier.SMALL])

    @staticmethod
    def _calculate_max_model_size(ram_mb: int, tier: HardwareTier) -> int:
        """Calculate maximum safe model size"""
        # Use 50% of RAM for model, rest for OS and processing
        safe_ram = ram_mb * 0.5

        # Add tier-specific limits
        tier_limits = {
            HardwareTier.NANO: 100,
            HardwareTier.TINY: 500,
            HardwareTier.SMALL: 2000,
            HardwareTier.MEDIUM: 8000,
            HardwareTier.LARGE: 16000,
            HardwareTier.XLARGE: 50000
        }

        return min(int(safe_ram), tier_limits.get(tier, 2000))

    @staticmethod
    def _determine_optimal_backend(platform: str, arch: str, has_gpu: bool,
                                   has_metal: bool, has_cuda: bool) -> str:
        """Determine optimal inference backend"""
        if has_cuda and has_gpu:
            return "vllm"  # Best for NVIDIA GPUs

        if has_metal:
            return "llama.cpp-metal"  # Best for Apple Silicon

        if platform == 'linux' and 'arm' in arch:
            return "llama.cpp"  # Best for ARM (Pi)

        if platform == 'windows':
            return "llama.cpp"  # Most compatible on Windows

        return "llama.cpp"  # Default safe choice


def print_hardware_report(info: HardwareInfo):
    """Print formatted hardware report"""
    print("\n" + "="*60)
    print("CH8 AGENT - HARDWARE DETECTION REPORT")
    print("="*60)

    print(f"\n📱 PLATFORM")
    print(f"  OS: {info.platform.title()} {info.os_version}")
    print(f"  Architecture: {info.architecture} ({'64-bit' if info.is_64bit else '32-bit'})")

    if info.is_raspberry_pi:
        print(f"  Device: Raspberry Pi {info.pi_model}")

    print(f"\n🔧 CPU")
    print(f"  Model: {info.cpu_model}")
    print(f"  Cores: {info.cpu_cores} ({info.cpu_threads} threads)")
    if info.cpu_freq_mhz:
        print(f"  Frequency: {info.cpu_freq_mhz:.0f} MHz")

    print(f"\n💾 MEMORY")
    print(f"  RAM Total: {info.ram_total_mb:,} MB")
    print(f"  RAM Available: {info.ram_available_mb:,} MB ({info.ram_available_mb/info.ram_total_mb*100:.1f}%)")
    print(f"  Swap: {info.swap_total_mb:,} MB")

    print(f"\n💽 STORAGE")
    print(f"  Total: {info.storage_total_gb:.1f} GB")
    print(f"  Available: {info.storage_available_gb:.1f} GB")

    if info.has_gpu:
        print(f"\n🎮 GPU")
        print(f"  Type: {info.gpu_type}")
        if info.gpu_vram_mb:
            print(f"  VRAM: {info.gpu_vram_mb:,} MB")
        if info.has_cuda:
            print(f"  CUDA: Available")
        if info.has_metal:
            print(f"  Metal: Available")

    print(f"\n⚡ CAPABILITIES")
    print(f"  Tier: {info.tier.value.upper()}")
    print(f"  Max Model Size: {info.max_model_size_mb:,} MB")
    print(f"  Optimal Backend: {info.optimal_backend}")

    print(f"\n🎯 RECOMMENDED MODELS")
    for model in info.recommended_models:
        print(f"  • {model.name}")
        print(f"    Size: {model.size_mb} MB | Quant: {model.quantization} | "
              f"Backend: {model.backend}")
        print(f"    Use: {model.use_case}")

    print("\n" + "="*60)


if __name__ == "__main__":
    info = HardwareDetector.detect()
    print_hardware_report(info)
