from __future__ import annotations

import platform
from pathlib import Path


def detect_os() -> str:
    """Detect whether we're running on WSL2, macOS, or Linux."""
    if platform.system() == "Darwin":
        return "mac"
    proc_version = Path("/proc/version")
    if proc_version.exists():
        text = proc_version.read_text().lower()
        if "microsoft" in text:
            return "wsl2"
    return "linux"
