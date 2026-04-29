"""Allows running the daemon directly: python -m connect.daemon"""
import asyncio
import logging
import sys
from .daemon import _main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

try:
    asyncio.run(_main())
except RuntimeError as e:
    if "Not authenticated" in str(e):
        print(f"\n  ERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    raise
