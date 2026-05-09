#!/usr/bin/env python3

import os
import sys
import json
import time
import signal
import logging
from pathlib import Path
from datetime import datetime
from subprocess import run, PIPE

sys.path.insert(0, str(Path(__file__).parent.parent))

AGENT_NAME = "error_log_collector"
CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / f"{AGENT_NAME}.pid"
LOG_FILE = CONFIG_DIR / f"{AGENT_NAME}.log"
STATE_FILE = CONFIG_DIR / "state.json"
MASTER_LOG_DIR = Path("/tmp/logs")

running = True

def signal_handler(signum, frame):
    global running
    running = False
    logging.info(f"Received signal {signum}, shutting down...")

def setup_logging():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )

def write_pid():
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()

def register_state():
    state = {}
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    
    state[AGENT_NAME] = {
        "pid": os.getpid(),
        "status": "running",
        "last_update": datetime.now().isoformat()
    }
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def collect_logs():
    logs = {}
    log_sources = {
        "syslog": "/var/log/syslog",
        "kern": "/var/log/kern.log",
        "nginx_error": "/var/log/nginx/error.log"
    }
    
    for name, path in log_sources.items():
        if Path(path).exists():
            result = run(["tail", "-n", "50", path], stdout=PIPE, stderr=PIPE, text=True)
            if result.returncode == 0:
                logs[name] = result.stdout
    
    result = run(["docker", "ps", "-q"], stdout=PIPE, stderr=PIPE, text=True)
    if result.returncode == 0:
        container_ids = result.stdout.strip().split('\n')
        docker_logs = []
        for cid in container_ids[:5]:
            if cid:
                log_result = run(["docker", "logs", "--tail", "20", cid], 
                               stdout=PIPE, stderr=PIPE, text=True)
                docker_logs.append(f"Container {cid}:\n{log_result.stderr}")
        logs["docker"] = "\n".join(docker_logs)
    
    return logs

def send_logs_to_master(logs):
    MASTER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hostname = run(["hostname"], stdout=PIPE, text=True).stdout.strip()
    
    for log_type, content in logs.items():
        log_file = MASTER_LOG_DIR / f"{hostname}_{log_type}_{timestamp}.log"
        with open(log_file, 'w') as f:
            f.write(content)
    
    logging.info(f"Sent {len(logs)} log files to {MASTER_LOG_DIR}")

def main():
    global running
    
    setup_logging()
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    write_pid()
    logging.info(f"{AGENT_NAME} started with PID {os.getpid()}")
    
    last_register = 0
    last_collect = 0
    
    try:
        while running:
            current_time = time.time()
            
            if current_time - last_register >= 30:
                register_state()
                last_register = current_time
            
            if current_time - last_collect >= 60:
                logs = collect_logs()
                send_logs_to_master(logs)
                last_collect = current_time
            
            time.sleep(1)
    
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
    finally:
        remove_pid()
        logging.info(f"{AGENT_NAME} stopped")

if __name__ == "__main__":
    main()
