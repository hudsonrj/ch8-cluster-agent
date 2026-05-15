#!/usr/bin/env python3

import os
import sys
import json
import time
import hashlib
import argparse
import logging
import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
from statistics import mean, stdev
from typing import Dict, List, Tuple, Optional

class FileIntegrityMonitor:
    def __init__(self, config_file: str = "fim_config.json", db_file: str = "fim_database.db"):
        self.config_file = config_file
        self.db_file = db_file
        self.config = self._load_config()
        self.db_conn = None
        self.running = False
        self.change_patterns = defaultdict(list)
        self.alert_history = deque(maxlen=1000)
        self.baseline_established = False
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fim.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self._init_database()
        self._load_baseline()

    def _load_config(self) -> Dict:
        default_config = {
            "monitored_paths": [
                "/etc/passwd",
                "/etc/shadow",
                "/etc/hosts",
                "/etc/crontab",
                "/boot",
                "/usr/bin",
                "/usr/sbin"
            ],
            "excluded_extensions": [".log", ".tmp", ".cache", ".pid"],
            "scan_interval": 300,
            "alert_threshold": 0.7,
            "learning_period_days": 7,
            "max_file_size_mb": 100,
            "enable_realtime": True,
            "suspicious_patterns": [
                "shadow",
                "passwd",
                "sudoers",
                "authorized_keys",
                "crontab"
            ]
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                self.logger.warning(f"Error loading config: {e}, using defaults")
        else:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
        
        return default_config

    def _init_database(self):
        self.db_conn = sqlite3.connect(self.db_file, check_same_thread=False)
        cursor = self.db_conn.cursor()
        
        # File baseline table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_baseline (
                path TEXT PRIMARY KEY,
                sha256_hash TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                permissions TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Change history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                old_hash TEXT,
                new_hash TEXT,
                change_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                suspicious_score REAL DEFAULT 0.0,
                alert_generated BOOLEAN DEFAULT FALSE
            )
        ''')
        
        # Pattern learning table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS change_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path_pattern TEXT NOT NULL,
                hour_of_day INTEGER,
                day_of_week INTEGER,
                change_frequency REAL,
                legitimacy_score REAL DEFAULT 0.5,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.db_conn.commit()

    def _calculate_sha256(self, file_path: str) -> Optional[str]:
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating hash for {file_path}: {e}")
            return None

    def _get_file_info(self, file_path: str) -> Optional[Dict]:
        try:
            stat = os.stat(file_path)
            file_hash = self._calculate_sha256(file_path)
            if file_hash is None:
                return None
            
            return {
                'path': file_path,
                'hash': file_hash,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'permissions': oct(stat.st_mode)[-3:]
            }
        except Exception as e:
            self.logger.error(f"Error getting file info for {file_path}: {e}")
            return None

    def _should_monitor_file(self, file_path: str) -> bool:
        path_obj = Path(file_path)
        
        # Check file size
        try:
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb > self.config['max_file_size_mb']:
                return False
        except:
            return False
        
        # Check excluded extensions
        if path_obj.suffix in self.config['excluded_extensions']:
            return False
        
        # Skip temporary files
        if any(temp in path_obj.name for temp in ['.tmp', '.temp', '.swp', '~']):
            return False
        
        return True

    def _scan_directory(self, directory: str) -> List[str]:
        files = []
        try:
            for root, dirs, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    if os.path.isfile(file_path) and self._should_monitor_file(file_path):
                        files.append(file_path)
        except Exception as e:
            self.logger.error(f"Error scanning directory {directory}: {e}")
        
        return files

    def _get_monitored_files(self) -> List[str]:
        files = []
        for path in self.config['monitored_paths']:
            if os.path.isfile(path):
                if self._should_monitor_file(path):
                    files.append(path)
            elif os.path.isdir(path):
                files.extend(self._scan_directory(path))
        
        return files

    def _load_baseline(self):
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM file_baseline")
        count = cursor.fetchone()[0]
        
        if count > 0:
            self.baseline_established = True
            self.logger.info(f"Loaded baseline with {count} files")
        else:
            self.logger.info("No baseline found, will establish on first scan")

    def establish_baseline(self):
        self.logger.info("Establishing file integrity baseline...")
        files = self._get_monitored_files()
        
        cursor = self.db_conn.cursor()
        baseline_count = 0
        
        for file_path in files:
            file_info = self._get_file_info(file_path)
            if file_info:
                cursor.execute('''
                    INSERT OR REPLACE INTO file_baseline 
                    (path, sha256_hash, size, mtime, permissions, last_verified)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    file_info['path'],
                    file_info['hash'],
                    file_info['size'],
                    file_info['mtime'],
                    file_info['permissions']
                ))
                baseline_count += 1
        
        self.db_conn.commit()
        self.baseline_established = True
        self.logger.info(f"Baseline established with {baseline_count} files")

    def _calculate_suspicion_score(self, file_path: str, change_type: str) -> float:
        score = 0.0
        
        # Base score by change type
        change_scores = {
            'modified': 0.3,
            'deleted': 0.7,
            'new': 0.4,
            'permissions': 0.5
        }
        score += change_scores.get(change_type, 0.3)
        
        # Check for suspicious patterns in path
        for pattern in self.config['suspicious_patterns']:
            if pattern in file_path.lower():
                score += 0.3
                break
        
        # Time-based analysis
        now = datetime.now()
        if now.hour < 6 or now.hour > 22:  # Night time changes more suspicious
            score += 0.2
        
        # Historical pattern analysis
        cursor = self.db_conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM change_history 
            WHERE path = ? AND timestamp > datetime('now', '-7 days')
        ''', (file_path,))
        
        recent_changes = cursor.fetchone()[0]
        if recent_changes > 5:  # Frequent changes less suspicious
            score -= 0.2
        elif recent_changes == 0:  # First time change more suspicious
            score += 0.2
        
        return min(1.0, max(0.0, score))

    def _generate_alert(self, file_path: str, change_type: str, suspicion_score: float, details: Dict):
        alert = {
            'timestamp': datetime.now().isoformat(),
            'file_path': file_path,
            'change_type': change_type,
            'suspicion_score': suspicion_score,
            'details': details,
            'alert_level': 'HIGH' if suspicion_score > 0.7 else 'MEDIUM' if suspicion_score > 0.4 else 'LOW'
        }
        
        self.alert_history.append(alert)
        
        log_msg = f"ALERT [{alert['alert_level']}] {change_type.upper()} - {file_path} (Score: {suspicion_score:.2f})"
        if alert['alert_level'] == 'HIGH':
            self.logger.critical(log_msg)
        elif alert['alert_level'] == 'MEDIUM':
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)
        
        # Update change history
        cursor = self.db_conn.cursor()
        cursor.execute('''
            UPDATE change_history 
            SET alert_generated = TRUE 
            WHERE path = ? AND timestamp = (
                SELECT MAX(timestamp) FROM change_history WHERE path = ?
            )
        ''', (file_path, file_path))
        self.db_conn.commit()

    def _record_change(self, file_path: str, change_type: str, old_hash: str = None, new_hash: str = None):
        suspicion_score = self._calculate_suspicion_score(file_path, change_type)
        
        cursor = self.db_conn.cursor()
        cursor.execute('''
            INSERT INTO change_history 
            (path, old_hash, new_hash, change_type, suspicious_score)
            VALUES (?, ?, ?, ?, ?)
        ''', (file_path, old_hash, new_hash, change_type, suspicion_score))
