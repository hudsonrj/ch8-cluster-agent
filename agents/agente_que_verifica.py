#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
import os
import signal
import time
import subprocess
from datetime import datetime

AGENT_NAME = "agente_que_verifica"
CONFIG_DIR = Path.home() / ".config" / "ch8"
PID_FILE = CONFIG_DIR / f"{AGENT_NAME}.pid"
LOG_FILE = CONFIG_DIR / f"{AGENT_NAME}.log"
STATE_FILE = CONFIG_DIR / "state.json"

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
    logging.info(f"PID {os.getpid()} written to {PID_FILE}")

def remove_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()
        logging.info(f"Removed PID file {PID_FILE}")

def update_state(status, task, details=None):
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        else:
            state = {"agents": []}
        
        agent_entry = {
            "name": AGENT_NAME,
            "status": status,
            "task": task,
            "model": "rule-based",
            "platform": "custom",
            "autonomous": True,
            "updated_at": int(time.time()),
            "tools": ["oracle_check", "performance_monitor"],
            "details": details or {}
        }
        
        agents = [a for a in state.get("agents", []) if a.get("name") != AGENT_NAME]
        agents.append(agent_entry)
        state["agents"] = agents
        
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        
    except Exception as e:
        logging.error(f"Failed to update state: {e}")

def check_oracle_performance():
    details = {}
    try:
        result = subprocess.run(
            ["pgrep", "-f", "oracle"],
            capture_output=True,
            text=True,
            timeout=5
        )
        oracle_running = bool(result.stdout.strip())
        details["oracle_processes"] = len(result.stdout.strip().split('\n')) if oracle_running else 0
        
        if oracle_running:
            ps_result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5
            )
            oracle_lines = [line for line in ps_result.stdout.split('\n') if 'oracle' in line.lower()]
            details["oracle_status"] = "running"
            details["process_count"] = len(oracle_lines)
        else:
            details["oracle_status"] = "not_running"
        
        load_result = subprocess.run(
            ["uptime"],
            capture_output=True,
            text=True,
            timeout=5
        )
        details["system_load"] = load_result.stdout.strip()
        
        return "ok" if oracle_running else "warning", details
        
    except subprocess.TimeoutExpired:
        logging.error("Oracle check timed out")
        return "error", {"error": "timeout"}
    except Exception as e:
        logging.error(f"Oracle check failed: {e}")
        return "error", {"error": str(e)}

def main():
    global running
    
    setup_logging()
    logging.info(f"Starting {AGENT_NAME}")
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    write_pid()
    
    last_update = 0
    
    try:
        while running:
            current_time = time.time()
            
            if current_time - last_update >= 30:
                logging.info("Performing Oracle verification check")
                status_result, details = check_oracle_performance()
                
                if status_result == "ok":
                    update_state("running", "Monitoring Oracle - All OK", details)
                    logging.info(f"Oracle check passed: {details}")
                elif status_result == "warning":
                    update_state("idle", "Oracle not detected", details)
                    logging.warning(f"Oracle warning: {details}")
                else:
                    update_state("error", "Oracle check failed", details)
                    logging.error(f"Oracle check error: {details}")
                
                last_update = current_time
            
            time.sleep(1)
    
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {e}")
        update_state("error", f"Fatal error: {str(e)}", {"error": str(e)})
    
    finally:
        remove_pid()
        logging.info(f"{AGENT_NAME} stopped")

if __name__ == "__main__":
    main()
