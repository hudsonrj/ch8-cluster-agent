"""
CH8 Daemon — Android Foreground Service

This runs as a Kivy background service, keeping the daemon alive
even when the app is in the background.
"""

import os
import sys
import asyncio
import logging

# Set up paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

# Android app private storage
try:
    from android.storage import app_storage_path
    STORAGE_DIR = app_storage_path()
except ImportError:
    STORAGE_DIR = APP_DIR

from pathlib import Path
CONFIG_DIR = Path(STORAGE_DIR) / ".config" / "ch8"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Set environment BEFORE importing connect modules
os.environ["HOME"] = STORAGE_DIR
os.environ["CH8_CONFIG_DIR"] = str(CONFIG_DIR)
os.environ.setdefault("PYTHONPATH", APP_DIR)

# Configure logging to file
LOG_FILE = CONFIG_DIR / "daemon.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode='a'),
    ]
)
log = logging.getLogger("ch8.service")
log.info("CH8 foreground service starting")

# Android service setup
try:
    from jnius import autoclass
    PythonService = autoclass('org.kivy.android.PythonService')
    PythonService.mService.setAutoRestartService(True)
    log.info("Auto-restart enabled")
except Exception as e:
    log.warning(f"Could not configure auto-restart: {e}")

# Run the daemon
from connect.daemon import _main

if __name__ == '__main__':
    try:
        asyncio.run(_main())
    except SystemExit:
        log.error("Daemon exited (not authenticated?)")
    except Exception as e:
        log.error(f"Daemon crashed: {e}", exc_info=True)
