from __future__ import annotations

import json
import subprocess

from rich import print as rprint

from devmesh.models import Config


def tailscale_status() -> dict | None:
    """Get tailscale status as parsed JSON. Returns None if not available."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return None


def get_tailscale_ip() -> str:
    """Get this machine's Tailscale IPv4 address."""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def detect_tailscale(cfg: Config) -> None:
    """Update config with current Tailscale state."""
    ip = get_tailscale_ip()
    cfg.tailscale.installed = bool(ip)
    cfg.tailscale.ip = ip


def print_install_guide(os_type: str) -> None:
    """Print platform-specific Tailscale install instructions."""
    instructions = {
        "wsl2": (
            "[bold]Install Tailscale on WSL2:[/bold]\n"
            "  curl -fsSL https://tailscale.com/install.sh | sh\n"
            "  sudo tailscale up\n"
            "\n"
            "[dim]Note: Tailscale runs inside WSL2. Services are reachable\n"
            "directly via the Tailscale IP without netsh port forwarding.[/dim]"
        ),
        "linux": (
            "[bold]Install Tailscale on Linux:[/bold]\n"
            "  curl -fsSL https://tailscale.com/install.sh | sh\n"
            "  sudo tailscale up"
        ),
        "mac": (
            "[bold]Install Tailscale on macOS:[/bold]\n"
            "  brew install --cask tailscale\n"
            "  # Or download from https://tailscale.com/download/mac\n"
            "  # Then open Tailscale from Applications and sign in"
        ),
    }
    rprint(instructions.get(os_type, instructions["linux"]))
