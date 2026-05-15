import argparse
import json
import os
import socket
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

try:
    import psutil
except ImportError:
    psutil = None

class SmartPortSecurityScanner:
    def __init__(self, config_file="port_security_config.json", history_file="port_history.json"):
        self.config_file = config_file
        self.history_file = history_file
        self.config = self.load_config()
        self.history = self.load_history()
        
    def load_config(self):
        default_config = {
            "sensitive_ports": [22, 23, 25, 53, 80, 110, 143, 443, 993, 995, 3389, 5432, 3306],
            "whitelist_processes": ["sshd", "nginx", "apache2", "httpd", "mysqld", "postgres"],
            "scan_interval": 300,
            "alert_threshold": 3,
            "history_retention_days": 30
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
            except:
                pass
        else:
            self.save_config(default_config)
            
        return default_config
    
    def save_config(self, config):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"scans": [], "baselines": {}}
    
    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def get_open_ports_netstat(self):
        ports = []
        try:
            if os.name == 'nt':
                result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
            else:
                result = subprocess.run(['netstat', '-tuln'], capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                if 'LISTEN' in line or 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        addr = parts[3] if os.name != 'nt' else parts[1]
                        if ':' in addr:
                            port_str = addr.split(':')[-1]
                            try:
                                port = int(port_str)
                                ports.append(port)
                            except ValueError:
                                continue
        except Exception as e:
            print(f"Error running netstat: {e}")
        
        return list(set(ports))
    
    def get_open_ports_psutil(self):
        ports = []
        if not psutil:
            return ports
            
        try:
            connections = psutil.net_connections(kind='inet')
            for conn in connections:
                if conn.status == psutil.CONN_LISTEN and conn.laddr:
                    ports.append(conn.laddr.port)
        except Exception as e:
            print(f"Error using psutil: {e}")
            
        return list(set(ports))
    
    def get_process_for_port(self, port):
        if psutil:
            try:
                connections = psutil.net_connections(kind='inet')
                for conn in connections:
                    if (conn.status == psutil.CONN_LISTEN and 
                        conn.laddr and conn.laddr.port == port and conn.pid):
                        try:
                            proc = psutil.Process(conn.pid)
                            return {
                                "pid": conn.pid,
                                "name": proc.name(),
                                "cmdline": " ".join(proc.cmdline()[:3])
                            }
                        except:
                            continue
            except Exception as e:
                print(f"Error getting process for port {port}: {e}")
        
        try:
            if os.name == 'nt':
                result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True)
            else:
                result = subprocess.run(['lsof', '-i', f':{port}'], capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                if str(port) in line and ('LISTEN' in line or 'LISTENING' in line):
                    parts = line.split()
                    if os.name == 'nt' and len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            pid_int = int(pid)
                            proc_result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], 
                                                       capture_output=True, text=True)
                            proc_lines = proc_result.stdout.split('\n')
                            if len(proc_lines) > 3:
                                proc_parts = proc_lines[3].split()
                                if len(proc_parts) > 0:
                                    return {"pid": pid_int, "name": proc_parts[0], "cmdline": proc_parts[0]}
                        except:
                            continue
                    elif not os.name == 'nt' and len(parts) >= 2:
                        return {"pid": parts[1], "name": parts[0], "cmdline": parts[0]}
        except Exception as e:
            print(f"Error getting process info: {e}")
        
        return {"pid": "unknown", "name": "unknown", "cmdline": "unknown"}
    
    def scan_ports(self):
        open_ports = self.get_open_ports_psutil()
        if not open_ports:
            open_ports = self.get_open_ports_netstat()
        
        scan_result = {
            "timestamp": datetime.now().isoformat(),
            "ports": []
        }
        
        for port in sorted(open_ports):
            process_info = self.get_process_for_port(port)
            port_info = {
                "port": port,
                "process": process_info,
                "is_sensitive": port in self.config["sensitive_ports"],
                "is_whitelisted": any(wp in str(process_info.get("name", "")).lower() 
                                    for wp in self.config["whitelist_processes"])
            }
            scan_result["ports"].append(port_info)
        
        return scan_result
    
    def analyze_changes(self, current_scan):
        if not self.history["scans"]:
            return {"new_ports": [], "closed_ports": [], "suspicious_processes": []}
        
        last_scan = self.history["scans"][-1]
        last_ports = {p["port"]: p for p in last_scan["ports"]}
        current_ports = {p["port"]: p for p in current_scan["ports"]}
        
        new_ports = []
        closed_ports = []
        suspicious_processes = []
        
        for port, info in current_ports.items():
            if port not in last_ports:
                new_ports.append(info)
                if info["is_sensitive"] and not info["is_whitelisted"]:
                    suspicious_processes.append(info)
        
        for port, info in last_ports.items():
            if port not in current_ports:
                closed_ports.append(info)
        
        for port, info in current_ports.items():
            if port in last_ports:
                last_info = last_ports[port]
                if (info["process"]["name"] != last_info["process"]["name"] and
                    info["is_sensitive"] and not info["is_whitelisted"]):
                    suspicious_processes.append(info)
        
        return {
            "new_ports": new_ports,
            "closed_ports": closed_ports,
            "suspicious_processes": suspicious_processes
        }
    
    def update_baseline(self, scan_result):
        baseline_key = datetime.now().strftime("%Y-%m-%d")
        if baseline_key not in self.history["baselines"]:
            self.history["baselines"][baseline_key] = defaultdict(int)
        
        for port_info in scan_result["ports"]:
            port = port_info["port"]
            process_name = port_info["process"]["name"]
            key = f"{port}:{process_name}"
            self.history["baselines"][baseline_key][key] += 1
    
    def cleanup_history(self):
        cutoff_date = datetime.now() - timedelta(days=self.config["history_retention_days"])
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        self.history["scans"] = [
            scan for scan in self.history["scans"]
            if scan["timestamp"] >= cutoff_str
        ]
        
        keys_to_remove = [
            key for key in self.history["baselines"].keys()
            if key < cutoff_str
        ]
        for key in keys_to_remove:
            del self.history["baselines"][key]
    
    def generate_report(self, scan_result, analysis):
        report = []
        report.append(f"Port Security Scan Report - {scan_result['timestamp']}")
        report.append("=" * 60)
        
        report.append(f"\nTotal open ports: {len(scan_result['ports'])}")
        
        sensitive_ports = [p for p in scan_result['ports'] if p['is_sensitive']]
        if sensitive_ports:
            report.append(f"\nSensitive ports ({len(sensitive_ports)}):")
            for port_info in sensitive_ports:
                status = "WHITELISTED" if port_info["is_whitelisted"] else "ALERT"
                report.append(f"  Port {port_info['port']}: {port_info['process']['name']} [{status}]")
        
        if analysis["new_ports"]:
            report.append(f"\nNew ports detected ({len(analysis['new_ports'])}):")
            for port_info in analysis["new_ports"]:
                report.append(f"  Port {port_info['port']}: {port_info['process']['name']}")
        
        if analysis["closed_ports"]:
            report.append(f"\nClosed ports ({len(analysis['closed_ports'])}):")
            for port_info in analysis["closed_ports"]:
                report.append(f"  Port {port_info['port']}: {port_info['process']['name']}")
        
        if analysis["suspicious_processes"]:
            report.append(f"\nSUSPICIOUS ACTIVITY DETECTED ({len(analysis['suspicious_processes'])}):")
            for port_info in analysis["suspicious_processes"]:
                report.append(f"  Port {port_info['port']}: {port_info['process']['name']} - NOT WHITELISTED")
        
        return "\n".join(report)
    
    def run_scan(self):
        print("Starting port security scan...")
        
        scan_result = self.scan_ports()
        analysis = self.analyze_changes(scan_result)
        
        self.history["scans"].append(scan_result)
        self.update_baseline(scan_result)
        self
