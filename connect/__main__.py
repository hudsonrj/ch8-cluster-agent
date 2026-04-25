"""Allows running the daemon directly: python -m connect.daemon"""
import asyncio
import logging
from .daemon import _main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

asyncio.run(_main())
