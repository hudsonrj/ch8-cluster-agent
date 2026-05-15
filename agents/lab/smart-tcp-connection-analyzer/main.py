#!/usr/bin/env python3
import argparse
import socket
import sys
import time
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple
import subprocess
import os

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class ConnectionStats:
    state: str
    local_addr: str
    remote_addr: str
    pid: int = 0
    process_name: str = ""


class TCPConnectionAnalyzer:
    TCP_STATES = {
        'ESTABLISHED': 'Conexão ativa estabelecida',
        'SYN_SENT': 'Tentativa de conexão ativa',
        'SYN_RECV': 'Conexão sendo estabelecida',
        'FIN_WAIT1': 'Fechamento iniciado localmente',
        'FIN_WAIT2': 'Aguardando FIN remoto',
        'TIME_WAIT': 'Aguardando timeout após fechamento',
        'CLOSE': 'Fechada',
        'CLOSE_WAIT': 'Aguardando fechamento local',
        'LAST_ACK': 'Aguardando ACK final',
        'LISTEN': 'Escutando por conexões',
        'CLOSING': 'Fechamento simultâneo'
    }
    
    SUSPICIOUS_THRESHOLDS = {
        'TIME_WAIT': 1000,
        'CLOSE_WAIT': 100,
        'FIN_WAIT1': 50,
        'FIN_WAIT2': 50,
        'SYN_RECV': 200
    }

    def __init__(self):
        self.connections: List[ConnectionStats] = []
        self.state_counter: Counter = Counter()
        self.process_counter: Counter = Counter()
        self.port_counter: Counter = Counter()

    def collect_connections_psutil(self) -> List[ConnectionStats]:
        connections = []
        try:
            for conn in psutil.net_connections(kind='tcp'):
                if conn.status == 'NONE':
                    continue
                    
                local_addr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "unknown"
                remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "unknown"
                
                process_name = ""
                if conn.pid:
                    try:
                        proc = psutil.Process(conn.pid)
                        process_name = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        process_name = f"pid:{conn.pid}"
                
                connections.append(ConnectionStats(
                    state=conn.status,
                    local_addr=local_addr,
                    remote_addr=remote_addr,
                    pid=conn.pid or 0,
                    process_name=process_name
                ))
        except Exception as e:
            print(f"Erro ao coletar conexões com psutil: {e}", file=sys.stderr)
        
        return connections

    def collect_connections_netstat(self) -> List[ConnectionStats]:
        connections = []
        try:
            if sys.platform.startswith('linux'):
                result = subprocess.run(['ss', '-tan'], capture_output=True, text=True, timeout=5)
                if result.returncode != 0:
                    result = subprocess.run(['netstat', '-tan'], capture_output=True, text=True, timeout=5)
            elif sys.platform == 'darwin':
                result = subprocess.run(['netstat', '-tan'], capture_output=True, text=True, timeout=5)
            elif sys.platform == 'win32':
                result = subprocess.run(['netstat', '-an', '-p', 'tcp'], capture_output=True, text=True, timeout=5)
            else:
                return connections
            
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                
                if sys.platform == 'win32':
                    if len(parts) >= 4 and parts[0].upper() == 'TCP':
                        local_addr = parts[1]
                        remote_addr = parts[2]
                        state = parts[3]
                else:
                    local_addr = parts[3] if len(parts) > 3 else parts[0]
                    remote_addr = parts[4] if len(parts) > 4 else parts[1]
                    state = parts[5] if len(parts) > 5 else parts[-1]
                
                state = state.upper().replace('-', '_')
                if state not in self.TCP_STATES:
                    continue
                
                connections.append(ConnectionStats(
                    state=state,
                    local_addr=local_addr,
                    remote_addr=remote_addr
                ))
        except Exception as e:
            print(f"Erro ao coletar conexões com netstat/ss: {e}", file=sys.stderr)
        
        return connections

    def collect_connections(self):
        if HAS_PSUTIL:
            self.connections = self.collect_connections_psutil()
        else:
            self.connections = self.collect_connections_netstat()
        
        for conn in self.connections:
            self.state_counter[conn.state] += 1
            if conn.process_name:
                self.process_counter[conn.process_name] += 1
            
            try:
                local_port = conn.local_addr.split(':')[-1]
                if local_port.isdigit():
                    self.port_counter[int(local_port)] += 1
            except:
                pass

    def detect_suspicious_patterns(self) -> List[Tuple[str, str, int]]:
        issues = []
        
        for state, threshold in self.SUSPICIOUS_THRESHOLDS.items():
            count = self.state_counter.get(state, 0)
            if count > threshold:
                severity = "CRÍTICO" if count > threshold * 2 else "ALERTA"
                issues.append((severity, f"Muitas conexões em estado {state}", count))
        
        close_wait = self.state_counter.get('CLOSE_WAIT', 0)
        if close_wait > 50:
            issues.append(("CRÍTICO", "Possível vazamento de sockets (CLOSE_WAIT alto)", close_wait))
        
        syn_recv = self.state_counter.get('SYN_RECV', 0)
        if syn_recv > 100:
            issues.append(("ALERTA", "Possível ataque SYN flood", syn_recv))
        
        fin_wait = self.state_counter.get('FIN_WAIT1', 0) + self.state_counter.get('FIN_WAIT2', 0)
        if fin_wait > 100:
            issues.append(("ALERTA", "Muitas conexões em FIN_WAIT (fechamento lento)", fin_wait))
        
        half_open = (self.state_counter.get('SYN_SENT', 0) + 
                     self.state_counter.get('SYN_RECV', 0))
        if half_open > 200:
            issues.append(("ALERTA", "Muitas conexões half-open", half_open))
        
        return issues

    def suggest_kernel_optimizations(self) -> List[str]:
        suggestions = []
        
        time_wait = self.state_counter.get('TIME_WAIT', 0)
        if time_wait > 500:
            suggestions.append("net.ipv4.tcp_fin_timeout = 30  # Reduzir de 60s para 30s")
            suggestions.append("net.ipv4.tcp_tw_reuse = 1  # Permitir reutilização de sockets TIME_WAIT")
        
        close_wait = self.state_counter.get('CLOSE_WAIT', 0)
        if close_wait > 50:
            suggestions.append("# CLOSE_WAIT alto indica problema na aplicação (não fecha sockets)")
            suggestions.append("# Revisar código da aplicação para garantir close() adequado")
        
        syn_recv = self.state_counter.get('SYN_RECV', 0)
        if syn_recv > 100:
            suggestions.append("net.ipv4.tcp_max_syn_backlog = 4096  # Aumentar fila SYN")
            suggestions.append("net.ipv4.tcp_synack_retries = 2  # Reduzir retries SYN-ACK")
            suggestions.append("net.ipv4.tcp_syncookies = 1  # Ativar SYN cookies")
        
        total_conns = sum(self.state_counter.values())
        if total_conns > 5000:
            suggestions.append("net.core.somaxconn = 4096  # Aumentar fila de conexões")
            suggestions.append("net.ipv4.ip_local_port_range = 1024 65535  # Expandir range de portas")
        
        if not suggestions:
            suggestions.append("# Nenhuma otimização crítica necessária no momento")
        
        return suggestions

    def generate_report(self) -> str:
        report = []
        report.append("=" * 80)
        report.append("RELATÓRIO DE ANÁLISE DE CONEXÕES TCP")
        report.append("=" * 80)
        report.append(f"Data/Hora: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total de conexões: {len(self.connections)}")
        report.append("")
        
        report.append("ESTATÍSTICAS POR ESTADO:")
        report.append("-" * 80)
        for state in sorted(self.state_counter.keys()):
            count = self.state_counter[state]
            description = self.TCP_STATES.get(state, "Desconhecido")
            percentage = (count / len(self.connections) * 100) if self.connections else 0
            report.append(f"  {state:15} {count:6} ({percentage:5.1f}%)  - {description}")
        report.append("")
        
        if HAS_PSUTIL and self.process_counter:
            report.append("TOP 10 PROCESSOS POR NÚMERO DE CONEXÕES:")
            report.append("-" * 80)
            for process, count in self.process_counter.most_common(10):
                report.append(f"  {process:30} {count:6} conexões")
            report.append("")
        
        report.append("TOP 10 PORTAS LOCAIS MAIS UTILIZADAS:")
        report.append("-" * 80)
        for port, count in self.port_counter.most_common(10):
            report.append(f"  Porta {port:5}  {count:6} conexões")
        report.append("")
        
        issues = self.detect_suspicious_patterns()
        if issues:
            report.append("PADRÕES SUSPEITOS DETECTADOS:")
            report.append("-" * 80)
            for severity, description, count in issues:
                report.append(f"  [{severity}] {description}: {count}")
            report.append("")
        
        suggestions = self.suggest_kernel_optimizations()
        report.append("SUGESTÕES DE OTIMIZAÇÃO DO KERNEL:")
        report.append("-" * 80)
        for suggestion in suggestions:
            report.append(f"  {suggestion}")
        report.append("")
        
        if sys.platform.startswith('linux'):
            report.append
