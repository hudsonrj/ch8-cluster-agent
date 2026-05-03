"""
CH8 Connect Daemon (ch8d)

Runs in the background after `ch8 up`.
Responsibilities:
  - Register this node with the control server
  - Poll for peers every POLL_INTERVAL seconds
  - Maintain gRPC connections to active peers
  - Send heartbeats
  - Reconnect automatically on failure
"""

import asyncio
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .auth import CONFIG_DIR, get_access_token, get_network_id, get_node_id, is_authenticated
from .coordinator import ControlClient

# ------------------------------------------------------------------ #
# Tailscale integration

def get_tailscale_ip() -> Optional[str]:
    """Return this machine's Tailscale IP (100.x.x.x), or None if unavailable."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["tailscale", "ip", "--4"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode().strip()
        if out.startswith("100."):
            return out
    except Exception:
        pass
    return None


def check_tailscale() -> dict:
    """Check Tailscale status. Returns dict with 'installed', 'running', 'ip'."""
    result = {"installed": False, "running": False, "ip": None}
    try:
        import subprocess
        subprocess.check_output(["tailscale", "version"], timeout=3, stderr=subprocess.DEVNULL)
        result["installed"] = True
        ip = get_tailscale_ip()
        if ip:
            result["running"] = True
            result["ip"] = ip
    except FileNotFoundError:
        pass
    except Exception:
        result["installed"] = True  # installed but not running
    return result



log = logging.getLogger("ch8.daemon")

# Cache for slow detections
_service_cache: list = []
_model_cache:   list = []
_last_slow_check: float = 0.0

PID_FILE        = CONFIG_DIR / "daemon.pid"
STATE_FILE      = CONFIG_DIR / "state.json"
POLL_INTERVAL   = int(os.environ.get("CH8_POLL_INTERVAL", "30"))  # seconds
HEARTBEAT_SECS  = int(os.environ.get("CH8_HEARTBEAT", "5"))
SERVICE_REFRESH = 60   # seconds between service/model re-detection
NODE_PORT       = int(os.environ.get("CH8_PORT", "7878"))


class ConnectDaemon:
    """
    The background daemon that keeps the cluster connected.
    """

    def __init__(self, advertise_addr: Optional[str] = None,
                 port: int = NODE_PORT,
                 capabilities: Optional[List[str]] = None):
        self.advertise_addr = advertise_addr
        self.port           = port
        self.capabilities   = capabilities or _detect_capabilities()
        self.control        = ControlClient(advertise_addr=advertise_addr, port=port)
        self.peers: Dict[str, dict] = {}   # node_id -> peer info
        self._stop_event    = asyncio.Event()
        self._registered    = False

    # ------------------------------------------------------------------ #
    # Public interface

    async def start(self) -> None:
        """Start the daemon — blocks until stopped."""
        if not is_authenticated():
            log.error("Not authenticated. Run `ch8 login` or `ch8 up --token TOKEN`")
            raise RuntimeError("Not authenticated. Run `ch8 login` or `ch8 up --token TOKEN`")

        _write_pid()
        log.info(f"CH8 daemon starting  node={get_node_id()}  port={self.port}")

        self._ha_master: Optional[object] = None
        self._ha_standby: Optional[object] = None

        try:
            # Initial registration
            await self._register()

            # Bootstrap HA role after successful registration
            ha_result = await asyncio.get_event_loop().run_in_executor(None, _bootstrap_ha_safe)
            role = ha_result.get("role", "worker")
            log.info(f"HA role: {role}")

            # Build task list based on role
            tasks = [
                self._heartbeat_loop(),
                self._peer_discovery_loop(),
                self._wait_for_stop(),
            ]

            if role == "master":
                standbys = ha_result.get("standbys", [])
                from .cluster_ha import MasterHA
                self._ha_master = MasterHA(standbys)
                tasks.append(self._ha_master.run())
            elif role == "standby":
                master = ha_result.get("master", {})
                from .cluster_ha import StandbyHA
                self._ha_standby = StandbyHA(master)
                tasks.append(self._ha_standby.run())

            # Run all background tasks concurrently
            await asyncio.gather(*tasks)
        finally:
            log.info("Daemon shutting down...")
            if self._ha_master:
                self._ha_master.stop()
            if self._ha_standby:
                self._ha_standby.stop()
            await self.control.deregister()
            await self.control.close()
            _clear_pid()
            _write_state({"status": "offline", "peers": []})

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------ #
    # Internals

    async def _register(self) -> None:
        while True:
            try:
                result = await self.control.register(self.capabilities)
                self._registered = True
                log.info(f"Registered with control server  network={get_network_id()}")
                _write_state({"status": "online", "peers": []})
                return
            except Exception as e:
                log.warning(f"Registration failed ({e}), retrying in 10s...")
                await asyncio.sleep(10)

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                metrics = _collect_metrics()
                ok = await self.control.heartbeat(metrics)
                if not ok:
                    log.warning("Heartbeat rejected — re-registering...")
                    await self._register()
            except Exception as e:
                log.warning(f"Heartbeat error: {e}")
            await asyncio.sleep(HEARTBEAT_SECS)

    async def _peer_discovery_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                peers = await self.control.get_peers()
                current_ids: Set[str] = {p["node_id"] for p in peers}
                previous_ids: Set[str] = set(self.peers.keys())

                # New nodes
                for peer in peers:
                    nid = peer["node_id"]
                    if nid not in self.peers:
                        log.info(f"New peer discovered: {nid}  ({peer.get('hostname', '?')})")
                    self.peers[nid] = peer

                # Lost nodes
                for lost_id in previous_ids - current_ids:
                    log.info(f"Peer gone: {lost_id}")
                    del self.peers[lost_id]

                _write_state({"status": "online", "peers": list(self.peers.values())})

            except Exception as e:
                log.warning(f"Peer discovery error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _wait_for_stop(self) -> None:
        await self._stop_event.wait()


# ------------------------------------------------------------------ #
# State helpers

def _write_pid() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _clear_pid() -> None:
    if PID_FILE.exists():
        PID_FILE.unlink()


def _write_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = CONFIG_DIR / "state.lock"
    try:
        import fcntl
        def _lock(f):   fcntl.flock(f, fcntl.LOCK_EX)
        def _unlock(f): fcntl.flock(f, fcntl.LOCK_UN)
    except ImportError:
        def _lock(f):   pass   # Windows: no flock, single-process anyway
        def _unlock(f): pass
    with open(lock_file, "w") as lf:
        _lock(lf)
        try:
            # Preserve agents written by external processes (orchestrator, monitors)
            existing = {}
            if STATE_FILE.exists():
                try:
                    existing = json.loads(STATE_FILE.read_text())
                except Exception:
                    pass
            # Keep existing agents unless we're explicitly overriding
            if "agents" not in state and "agents" in existing:
                state["agents"] = existing["agents"]
            state["updated_at"] = int(time.time())
            STATE_FILE.write_text(json.dumps(state, indent=2))
        finally:
            _unlock(lf)


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {"status": "offline", "peers": []}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"status": "offline", "peers": []}


def get_daemon_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def is_daemon_running() -> bool:
    pid = get_daemon_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        # Verify it's actually our daemon (not a recycled PID)
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore")
            if "connect.daemon" not in cmdline and "connect/daemon" not in cmdline:
                _clear_pid()
                return False
        except Exception:
            pass  # non-Linux or no /proc — trust os.kill
        return True
    except OSError:
        _clear_pid()
        return False


# ------------------------------------------------------------------ #
# Capability detection

def _detect_capabilities() -> List[str]:
    caps = ["worker"]
    # Ollama
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            caps.append("ollama")
    except Exception:
        pass
    # GPU
    try:
        import subprocess
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                      timeout=3, stderr=subprocess.DEVNULL)
        if out.strip():
            caps.append("gpu")
    except Exception:
        pass
    # Memory tier
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / 1e9
        if ram_gb >= 16:
            caps.append("high-memory")
        elif ram_gb >= 8:
            caps.append("medium-memory")
        else:
            caps.append("low-memory")
    except Exception:
        pass
    # Tailscale
    if get_tailscale_ip():
        caps.append("tailscale")
    return caps


def _detect_all_disks() -> list:
    """Detect all mounted disks/partitions with usage info."""
    try:
        import psutil
        disks = []
        seen_devices = set()
        for part in psutil.disk_partitions(all=False):
            # Skip duplicates and virtual filesystems
            if part.device in seen_devices:
                continue
            if part.fstype in ("squashfs", "tmpfs", "devtmpfs", "overlay"):
                continue
            seen_devices.add(part.device)
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mount": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / 1e9, 2),
                    "used_gb": round(usage.used / 1e9, 2),
                    "free_gb": round(usage.free / 1e9, 2),
                    "pct": round(usage.percent, 1),
                })
            except (PermissionError, OSError):
                pass
        return disks
    except Exception:
        return []


def _get_local_ip() -> str:
    """Get the LAN IP of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


def _collect_metrics() -> dict:
    metrics = {}
    try:
        import psutil
        cpu   = psutil.cpu_percent(interval=0.2)
        mem   = psutil.virtual_memory()
        cores = psutil.cpu_count(logical=True) or 1
        metrics["cpu_pct"]    = cpu
        metrics["cpu_cores"]  = cores
        metrics["mem_pct"]    = round(mem.percent, 1)
        metrics["mem_total_gb"] = round(mem.total / 1e9, 2)
        metrics["mem_used_gb"]  = round(mem.used  / 1e9, 2)

        # Primary disk (HOME)
        disk = psutil.disk_usage(os.environ.get("HOME", "/"))
        metrics["disk_pct"]      = round(disk.percent, 1)
        metrics["disk_total_gb"] = round(disk.total / 1e9, 2)
        metrics["disk_used_gb"]  = round(disk.used  / 1e9, 2)

        # All disks
        metrics["disks"] = _detect_all_disks()
    except Exception:
        pass

    # Local IP (LAN)
    metrics["local_ip"] = _get_local_ip()

    # Autonomy status
    try:
        _auto_file = CONFIG_DIR / "autonomy.json"
        if _auto_file.exists():
            metrics["autonomous"] = json.loads(_auto_file.read_text()).get("enabled", False)
    except Exception:
        pass

    global _service_cache, _model_cache, _last_slow_check
    now = time.time()
    if now - _last_slow_check >= SERVICE_REFRESH:
        _model_cache   = _detect_ollama_models()
        _service_cache = _detect_services()
        _last_slow_check = now
    metrics["models"]   = _model_cache
    metrics["services"] = _service_cache
    metrics["agents"]   = _read_agents_from_state()
    metrics["tools"]    = _read_tools_config()
    metrics["channels"] = _read_channels_config()
    # Include AI model so peers know what LLM this node is running
    try:
        from connect.ai_config import get_provider_info
        ai = get_provider_info()
        metrics["ai_model"]    = ai.get("model", "")
        metrics["ai_provider"] = ai.get("provider", "")
    except Exception:
        pass
    return metrics


def _read_tools_config() -> list:
    """Read enabled tools from tools_enabled.json."""
    tools_file = CONFIG_DIR / "tools_enabled.json"
    try:
        data = json.loads(tools_file.read_text())
        return data.get("enabled", [])
    except Exception:
        return []


def _read_channels_config() -> list:
    """Read configured channels from channels.json."""
    channels_file = CONFIG_DIR / "channels.json"
    try:
        channels = json.loads(channels_file.read_text())
        return [{"type": ch.get("type", "unknown"), "id": ch.get("chat_id") or ch.get("channel_id") or ch.get("type")} for ch in channels]
    except Exception:
        return []


def _read_agents_from_state() -> list:
    """Read agents registered by external monitor processes via state.json."""
    try:
        agents = json.loads(STATE_FILE.read_text()).get("agents", [])
        # Include agents updated in the last 35 minutes (covers 30min cycle intervals)
        cutoff = time.time() - 2100
        return [a for a in agents if a.get("updated_at", 0) > cutoff]
    except Exception:
        return []


def _detect_ollama_models() -> list:
    """Return list of available Ollama model names."""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def _detect_services() -> list:
    """Detect running services: Docker containers, databases, system services."""
    import subprocess as _sp
    services = []
    reported: set = set()  # lowercase names already added

    # Docker containers
    try:
        out = _sp.check_output(
            ["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"],
            timeout=5, stderr=_sp.DEVNULL
        ).decode().strip()
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            name, image, status, ports = (parts + ["", "", "", ""])[:4]
            name = name.strip()
            services.append({
                "type":   "docker",
                "name":   name,
                "image":  image.strip(),
                "status": "running" if "Up" in status else "stopped",
                "ports":  ports.strip(),
            })
            reported.add(name.lower())
    except Exception:
        pass

    # Process-based detection — covers Linux and macOS naming variants
    try:
        import psutil
        proc_names = {p.name().lower() for p in psutil.process_iter(["name"])}
        known = [
            # (substring to match in proc name, display label)
            ("postgres",     "PostgreSQL"),
            ("postmaster",   "PostgreSQL"),
            ("mysqld",       "MySQL"),
            ("mongod",       "MongoDB"),
            ("redis-server", "Redis"),
            ("nginx",        "Nginx"),
            ("httpd",        "Apache"),
            ("apache2",      "Apache"),
            ("caddy",        "Caddy"),
            ("ollama",       "Ollama"),
            ("tailscaled",   "Tailscale"),
            ("tailscale",    "Tailscale"),  # macOS app process
        ]
        seen_labels: set = set()
        for proc_key, label in known:
            if label in seen_labels:
                continue
            if any(proc_key in n for n in proc_names):
                if label.lower() not in reported:
                    services.append({"type": "process", "name": label, "status": "running"})
                    reported.add(label.lower())
                seen_labels.add(label)
    except Exception:
        pass

    # macOS: brew services (catches services not visible as processes yet)
    if platform.system() == "Darwin":
        try:
            out = _sp.check_output(
                ["brew", "services", "list"],
                timeout=8, stderr=_sp.DEVNULL
            ).decode()
            brew_map = {
                "postgresql": "PostgreSQL",
                "mysql":      "MySQL",
                "mongodb":    "MongoDB",
                "redis":      "Redis",
                "nginx":      "Nginx",
                "ollama":     "Ollama",
                "caddy":      "Caddy",
            }
            for line in out.splitlines()[1:]:  # skip header row
                parts = line.split()
                if len(parts) >= 2 and parts[1].lower() == "started":
                    svc = parts[0].lower()
                    for key, label in brew_map.items():
                        if key in svc and label.lower() not in reported:
                            services.append({"type": "brew", "name": label, "status": "running"})
                            reported.add(label.lower())
        except Exception:
            pass

    return services


# ------------------------------------------------------------------ #
# Entry point (used when running as a subprocess)

def _get_advertise_address() -> str:
    """
    Determine the best address to advertise to the control server.
    Priority:
      1. CH8_ADVERTISE_ADDR env var (explicit override)
      2. Tailscale IP (100.x.x.x — works across networks)
      3. Local LAN IP (fallback — same-network only)
    """
    # 1. Explicit override
    explicit = os.environ.get("CH8_ADVERTISE_ADDR")
    if explicit:
        log.info(f"Using explicit advertise address: {explicit}")
        return explicit

    # 2. Tailscale
    ts = check_tailscale()
    if ts["running"] and ts["ip"]:
        log.info(f"Using Tailscale IP: {ts['ip']}")
        return ts["ip"]

    if ts["installed"]:
        log.warning("Tailscale installed but not connected. Run: tailscale up")
    else:
        log.warning("Tailscale not found. Using LAN IP (same-network only).")
        log.warning("For cross-network: install Tailscale or set CH8_ADVERTISE_ADDR")

    # 3. LAN IP fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
        log.info(f"Using LAN IP: {lan_ip}")
        return lan_ip
    except Exception:
        return "127.0.0.1"


def _bootstrap_ha_safe() -> dict:
    """Run bootstrap_ha() safely — never raises, returns empty dict on error."""
    try:
        from .cluster_ha import bootstrap_ha
        return bootstrap_ha()
    except Exception as e:
        log.warning(f"HA bootstrap failed (non-fatal): {e}")
        return {"role": "worker"}


async def _main(advertise_addr=None, port=NODE_PORT, capabilities=None):
    # Auto-detect the best advertise address
    if advertise_addr is None:
        advertise_addr = _get_advertise_address()

    daemon = ConnectDaemon(
        advertise_addr=advertise_addr,
        port=port,
        capabilities=capabilities,
    )

    loop = asyncio.get_event_loop()
    # add_signal_handler is Unix-only; Windows raises NotImplementedError
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, daemon.stop)
    except NotImplementedError:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda s, f: daemon.stop())
            except (OSError, ValueError):
                pass

    await daemon.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    asyncio.run(_main())
