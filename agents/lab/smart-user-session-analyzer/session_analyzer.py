#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import random
import string

class SessionAnalyzer:
    def __init__(self, data_dir="./session_data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.sessions_file = self.data_dir / "sessions.json"
        self.alerts_file = self.data_dir / "alerts.json"
        self.config_file = self.data_dir / "config.json"
        
        self.sessions = self._load_sessions()
        self.alerts = self._load_alerts()
        self.config = self._load_config()
        
    def _load_sessions(self):
        if self.sessions_file.exists():
            with open(self.sessions_file, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_sessions(self):
        with open(self.sessions_file, 'w') as f:
            json.dump(self.sessions, f, indent=2)
    
    def _load_alerts(self):
        if self.alerts_file.exists():
            with open(self.alerts_file, 'r') as f:
                return json.load(f)
        return []
    
    def _save_alerts(self):
        with open(self.alerts_file, 'w') as f:
            json.dump(self.alerts, f, indent=2)
    
    def _load_config(self):
        default_config = {
            "max_session_duration_hours": 12,
            "max_simultaneous_sessions": 3,
            "unusual_hours_start": 22,
            "unusual_hours_end": 6,
            "max_failed_logins": 5,
            "failed_login_window_minutes": 15,
            "session_gap_threshold_minutes": 30
        }
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                loaded = json.load(f)
                default_config.update(loaded)
        else:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=2)
        return default_config
    
    def _generate_session_id(self):
        return hashlib.sha256(
            f"{time.time()}{random.random()}".encode()
        ).hexdigest()[:16]
    
    def _create_alert(self, alert_type, username, details, severity="medium"):
        alert = {
            "id": self._generate_session_id(),
            "timestamp": datetime.now().isoformat(),
            "type": alert_type,
            "username": username,
            "severity": severity,
            "details": details
        }
        self.alerts.append(alert)
        self._save_alerts()
        return alert
    
    def login(self, username, ip_address=None, location=None):
        timestamp = datetime.now().isoformat()
        session_id = self._generate_session_id()
        
        if username not in self.sessions:
            self.sessions[username] = {
                "active_sessions": [],
                "history": [],
                "failed_logins": []
            }
        
        user_data = self.sessions[username]
        
        session = {
            "session_id": session_id,
            "login_time": timestamp,
            "logout_time": None,
            "ip_address": ip_address or "127.0.0.1",
            "location": location or "unknown",
            "status": "active"
        }
        
        user_data["active_sessions"].append(session)
        self._save_sessions()
        
        self._check_simultaneous_sessions(username)
        self._check_unusual_hours(username, timestamp)
        self._check_location_anomaly(username, ip_address)
        
        return session_id
    
    def logout(self, username, session_id):
        if username not in self.sessions:
            return False
        
        user_data = self.sessions[username]
        timestamp = datetime.now().isoformat()
        
        for session in user_data["active_sessions"]:
            if session["session_id"] == session_id:
                session["logout_time"] = timestamp
                session["status"] = "closed"
                
                login_dt = datetime.fromisoformat(session["login_time"])
                logout_dt = datetime.fromisoformat(timestamp)
                duration_hours = (logout_dt - login_dt).total_seconds() / 3600
                session["duration_hours"] = duration_hours
                
                user_data["history"].append(session)
                user_data["active_sessions"].remove(session)
                self._save_sessions()
                
                self._check_session_duration(username, duration_hours)
                return True
        
        return False
    
    def failed_login(self, username, ip_address=None):
        timestamp = datetime.now().isoformat()
        
        if username not in self.sessions:
            self.sessions[username] = {
                "active_sessions": [],
                "history": [],
                "failed_logins": []
            }
        
        user_data = self.sessions[username]
        user_data["failed_logins"].append({
            "timestamp": timestamp,
            "ip_address": ip_address or "127.0.0.1"
        })
        
        self._save_sessions()
        self._check_failed_logins(username)
    
    def _check_simultaneous_sessions(self, username):
        user_data = self.sessions[username]
        active_count = len(user_data["active_sessions"])
        max_allowed = self.config["max_simultaneous_sessions"]
        
        if active_count > max_allowed:
            self._create_alert(
                "simultaneous_sessions",
                username,
                f"User has {active_count} active sessions (max: {max_allowed})",
                severity="high"
            )
    
    def _check_unusual_hours(self, username, timestamp):
        dt = datetime.fromisoformat(timestamp)
        hour = dt.hour
        
        start = self.config["unusual_hours_start"]
        end = self.config["unusual_hours_end"]
        
        is_unusual = False
        if start > end:
            is_unusual = hour >= start or hour < end
        else:
            is_unusual = start <= hour < end
        
        if is_unusual:
            self._create_alert(
                "unusual_hours",
                username,
                f"Login at unusual hour: {hour}:00",
                severity="medium"
            )
    
    def _check_session_duration(self, username, duration_hours):
        max_duration = self.config["max_session_duration_hours"]
        
        if duration_hours > max_duration:
            self._create_alert(
                "long_session",
                username,
                f"Session duration {duration_hours:.2f}h exceeds maximum {max_duration}h",
                severity="medium"
            )
    
    def _check_failed_logins(self, username):
        user_data = self.sessions[username]
        failed_logins = user_data["failed_logins"]
        
        if not failed_logins:
            return
        
        window_minutes = self.config["failed_login_window_minutes"]
        max_failed = self.config["max_failed_logins"]
        
        now = datetime.now()
        cutoff = now - timedelta(minutes=window_minutes)
        
        recent_failures = [
            f for f in failed_logins
            if datetime.fromisoformat(f["timestamp"]) > cutoff
        ]
        
        if len(recent_failures) >= max_failed:
            self._create_alert(
                "brute_force",
                username,
                f"{len(recent_failures)} failed logins in {window_minutes} minutes",
                severity="critical"
            )
    
    def _check_location_anomaly(self, username, ip_address):
        if not ip_address or username not in self.sessions:
            return
        
        user_data = self.sessions[username]
        history = user_data["history"]
        
        if len(history) < 3:
            return
        
        recent_ips = set()
        for session in history[-10:]:
            recent_ips.add(session.get("ip_address"))
        
        if ip_address not in recent_ips and len(recent_ips) > 0:
            self._create_alert(
                "new_location",
                username,
                f"Login from new IP address: {ip_address}",
                severity="medium"
            )
    
    def get_active_sessions(self, username=None):
        if username:
            if username in self.sessions:
                return self.sessions[username]["active_sessions"]
            return []
        
        all_active = {}
        for user, data in self.sessions.items():
            if data["active_sessions"]:
                all_active[user] = data["active_sessions"]
        return all_active
    
    def get_alerts(self, severity=None, username=None, limit=None):
        filtered = self.alerts
        
        if severity:
            filtered = [a for a in filtered if a["severity"] == severity]
        
        if username:
            filtered = [a for a in filtered if a["username"] == username]
        
        filtered.sort(key=lambda x: x["timestamp"], reverse=True)
        
        if limit:
            filtered = filtered[:limit]
        
        return filtered
    
    def get_user_statistics(self, username):
        if username not in self.sessions:
            return None
        
        user_data = self.sessions[username]
        history = user_data["history"]
        
        if not history:
            return {
                "username": username,
                "total_sessions": 0,
                "active_sessions": len(user_data["active_sessions"]),
                "failed_logins": len(user_data["failed_logins"])
            }
        
        durations = [s.get("duration_hours", 0) for s in history if "duration_hours" in s]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        login_hours = []
        for session in history:
            dt = datetime.fromisoformat(session["login_time"])
            login_hours.append(dt.hour)
        
        most_common_hour = max(set(login_hours), key=login_hours.count) if login_hours else 0
        
        unique_ips = set(s.get("ip_address") for s in history if s.get("ip_address"))
        
        return {
            "username": username,
            "total_sessions": len(history),
            "active_sessions": len(user_data["active_sessions"]),
            "failed_logins": len(user_data["failed_logins"]),
            "average_duration_hours": round(avg_duration, 2),
            "most_common_login_hour": most_common_hour,
            "unique_ip_addresses": len(unique_ips)
        }
    
    def cleanup_old_sessions(self, days=30):
        cutoff = datetime.now() - timedelta(days=days)
        cleaned = 0
        
        for username, user_data in self.sessions.items():
            original_count = len(user_data["history"])
            user_data["history"] = [
                s for s in user_data["history"]
                if datetime.fromisoformat(s["login_time"]) > cutoff
            ]
            cleaned += original_count - len(user_data["history"])
