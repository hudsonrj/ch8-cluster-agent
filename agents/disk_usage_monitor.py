#!/usr/bin/env python3

import os
import sys
import json
import time
import signal
import logging
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / "disk_usage_monitor.pid"
STATE_FILE = CONFIG_DIR / "state.json"
LOG_FILE = CONFIG_DIR / "disk_usage_monitor.log"
AGENT_NAME = "disk_usage_monitor"
THRESHOLD = 90

running = True


def signal_handler(signum, frame):
    global running
    running = False


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
    return logging.getLogger(AGENT_NAME)


def write_pid():
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def register_state(status, message=""):
    try:
        state = {}
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        
        if "agents" not in state:
            state["agents"] = {}
        
        state["agents"][AGENT_NAME] = {
            "pid": os.getpid(),
            "status": status,
            "last_update": datetime.now().isoformat(),
            "message": message
        }
        
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to register state: {e}")


def check_disk_usage():
    alerts = []
    partitions = ["/"]
    
    if Path("/home").is_mount():
        partitions.append("/home")
    
    for partition in partitions:
        try:
            usage = shutil.disk_usage(partition)
            percent = (usage.used / usage.total) * 100
            
            if percent >= THRESHOLD:
                alert_msg = f"ALERT: {partition} disk usage at {percent:.1f}%"
                alerts.append(alert_msg)
                logger.warning(alert_msg)
            else:
                logger.info(f"{partition} disk usage: {percent:.1f}%")
        except Exception as e:
            logger.error(f"Error checking {partition}: {e}")
    
    return alerts


def main():
    global logger
    logger = setup_logging()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    write_pid()
    logger.info(f"{AGENT_NAME} started with PID {os.getpid()}")
    
    last_register = 0
    
    try:
        while running:
            current_time = time.time()
            
            alerts = check_disk_usage()
            status = "alert" if alerts else "healthy"
            message = "; ".join(alerts) if alerts else "All partitions below threshold"
            
            if current_time - last_register >= 30:
                register_state(status, message)
                last_register = current_time
            
            time.sleep(60)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        register_state("error", str(e))
    finally:
        logger.info(f"{AGENT_NAME} shutting down")
        register_state("stopped", "Agent terminated")
        remove_pid()


if __name__ == "__main__":
    main()
