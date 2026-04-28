"""
CH8 Daemon — Android Foreground Service

This runs as a Kivy background service, keeping the daemon alive
even when the app is in the background.
"""

import os
import sys
import asyncio

# Set up paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
os.environ["HOME"] = APP_DIR
os.environ.setdefault("PYTHONPATH", APP_DIR)

from pathlib import Path
CONFIG_DIR = Path(APP_DIR) / ".config" / "ch8"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Android service setup
from jnius import autoclass

PythonService = autoclass('org.kivy.android.PythonService')
PythonService.mService.setAutoRestartService(True)

# Run the daemon
from connect.daemon import _main

if __name__ == '__main__':
    asyncio.run(_main())
