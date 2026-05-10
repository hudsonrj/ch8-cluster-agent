#!/usr/bin/env python3
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "ch8.pid"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "ch8.log"

running = True


def setup_logging():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("ch8")


def signal_handler(signum, frame):
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    logger.info(f"PID {os.getpid()} written to {PID_FILE}")


def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()
        logger.info("PID file removed")


def check_agent_running():
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True, pid
        except (OSError, ValueError):
            return False, None
    return False, None


def get_deployment_methods():
    return [
        "systemd",
        "docker",
        "kubernetes",
        "cron",
        "supervisor",
        "manual"
    ]


def register_state():
    is_running, pid = check_agent_running()
    state = {
        "agent_name": "ch8",
        "status": "running" if is_running else "stopped",
        "pid": os.getpid(),
        "timestamp": datetime.now().isoformat(),
        "deployment_methods": get_deployment_methods(),
        "config_dir": str(CONFIG_DIR),
        "log_file": str(LOG_FILE)
    }
    
    # Preserve agents list written by other processes
    import fcntl
    lock_file = CONFIG_DIR / "state.lock"
    with open(lock_file, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            existing = {}
            if STATE_FILE.exists():
                try:
                    existing = json.loads(STATE_FILE.read_text())
                except Exception:
                    pass
            if "agents" in existing:
                state["agents"] = existing["agents"]
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    
    logger.info(f"State registered: {state['status']}")
    return state


def main():
    global logger
    logger = setup_logging()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("CH8 agent starting...")
    
    is_running, existing_pid = check_agent_running()
    if is_running:
        logger.warning(f"Agent already running with PID {existing_pid}")
        sys.exit(1)
    
    write_pid()
    
    try:
        logger.info("Agent is running")
        logger.info(f"Available deployment methods: {', '.join(get_deployment_methods())}")
        
        last_register = 0
        while running:
            current_time = time.time()
            if current_time - last_register >= 30:
                register_state()
                last_register = current_time
            time.sleep(1)
    
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    
    finally:
        logger.info("Shutting down CH8 agent...")
        remove_pid()
        logger.info("CH8 agent stopped")


if __name__ == "__main__":
    main()
