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

class MemoryMonitor:
    def __init__(self):
        self.running = True
        self.config_dir = Path.home() / ".config" / "ch8"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.pid_file = self.config_dir / "memory_monitor.pid"
        self.state_file = self.config_dir / "state.json"
        self.log_file = self.config_dir / "memory_monitor.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("memory_monitor")
        
        self.last_state_update = 0
        self.check_interval = 60
        self.state_interval = 30
        self.threshold = 80
        
    def write_pid(self):
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        self.logger.info(f"PID {os.getpid()} written to {self.pid_file}")
    
    def remove_pid(self):
        if self.pid_file.exists():
            self.pid_file.unlink()
            self.logger.info("PID file removed")
    
    def get_memory_usage(self):
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            
            mem_info = {}
            for line in lines:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    mem_info[key] = int(value)
            
            total = mem_info.get('MemTotal', 0)
            available = mem_info.get('MemAvailable', 0)
            used = total - available
            usage_percent = (used / total * 100) if total > 0 else 0
            
            return {
                'total_kb': total,
                'used_kb': used,
                'available_kb': available,
                'usage_percent': round(usage_percent, 2)
            }
        except Exception as e:
            self.logger.error(f"Error reading memory info: {e}")
            return None
    
    def update_state(self, memory_info):
        try:
            state = {}
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
            
            state['memory_monitor'] = {
                'status': 'running',
                'pid': os.getpid(),
                'last_update': datetime.now().isoformat(),
                'memory': memory_info
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            self.logger.debug("State updated")
        except Exception as e:
            self.logger.error(f"Error updating state: {e}")
    
    def check_memory(self):
        memory_info = self.get_memory_usage()
        if not memory_info:
            return
        
        usage = memory_info['usage_percent']
        self.logger.info(f"Memory usage: {usage}%")
        
        if usage > self.threshold:
            self.logger.warning(f"ALERT: Memory usage {usage}% exceeds threshold {self.threshold}%")
        
        current_time = time.time()
        if current_time - self.last_state_update >= self.state_interval:
            self.update_state(memory_info)
            self.last_state_update = current_time
    
    def signal_handler(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def run(self):
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.write_pid()
        self.logger.info("Memory monitor started")
        
        try:
            while self.running:
                self.check_memory()
                time.sleep(self.check_interval)
        finally:
            self.remove_pid()
            self.logger.info("Memory monitor stopped")

def main():
    monitor = MemoryMonitor()
    monitor.run()

if __name__ == "__main__":
    main()
