"""Windows asyncio compatibility for Playwright subprocess spawning."""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """Use ProactorEventLoop on Windows so asyncio subprocess APIs work."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


configure_event_loop()
