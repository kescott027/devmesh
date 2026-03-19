from __future__ import annotations

import re
import subprocess

from rich import print as rprint
from rich.table import Table

from devmesh.models import Config, PortRule
from devmesh.platform_detect import detect_os


def list_listening_ports() -> list[dict]:
    """Parse ss -tlnp to get listening TCP ports."""
    result = subprocess.run(
        ["ss", "-tlnp"],
        capture_output=True, text=True,
    )
    ports = []
    for line in result.stdout.splitlines()[1:]:  # skip header
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[3]
        # Extract port from address like *:8080 or 127.0.0.1:8080 or [::]:8080
        match = re.search(r":(\d+)$", local)
        if match:
            port = int(match.group(1))
            process = parts[5] if len(parts) > 5 else ""
            # Extract process name from users:(("name",pid=X,...))
            proc_match = re.search(r'\("([^"]+)"', process)
            proc_name = proc_match.group(1) if proc_match else ""
            ports.append({"port": port, "address": local, "process": proc_name})
    return ports


def _get_wsl_ip() -> str:
    """Get the WSL2 eth0 IP address."""
    result = subprocess.run(
        ["ip", "addr", "show", "eth0"],
        capture_output=True, text=True,
    )
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", result.stdout)
    return match.group(1) if match else ""


def _netsh_rule_exists(port: int, proto: str = "tcp") -> bool:
    """Check if a netsh portproxy rule already exists for this port."""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "netsh interface portproxy show v4tov4"],
        capture_output=True, text=True,
    )
    pattern = rf"0\.0\.0\.0\s+{port}\s+"
    return bool(re.search(pattern, result.stdout))


def _firewall_rule_name(port: int, proto: str) -> str:
    return f"devmesh-{port}-{proto}"


def expose_port(cfg: Config, port: int, proto: str = "tcp") -> None:
    """Expose a WSL2 port to the LAN via netsh portproxy."""
    os_type = detect_os()

    if os_type != "wsl2":
        rprint("[yellow]Port forwarding via netsh is only needed on WSL2.[/yellow]")
        if cfg.tailscale.installed:
            rprint(f"[dim]Your Tailscale IP is {cfg.tailscale.ip} — services are directly reachable.[/dim]")
        return

    if cfg.tailscale.installed:
        rprint(f"[dim]Note: With Tailscale active, port {port} is already reachable at {cfg.tailscale.ip}:{port}[/dim]")

    wsl_ip = _get_wsl_ip()
    if not wsl_ip:
        rprint("[red]Could not determine WSL2 IP address[/red]")
        raise SystemExit(1)

    if _netsh_rule_exists(port, proto):
        rprint(f"[yellow]Port {port} is already forwarded[/yellow]")
        return

    rule_name = _firewall_rule_name(port, proto)

    # Build PowerShell commands
    portproxy_cmd = (
        f"netsh interface portproxy add v4tov4 "
        f"listenport={port} listenaddress=0.0.0.0 "
        f"connectport={port} connectaddress={wsl_ip}"
    )
    firewall_cmd = (
        f"netsh advfirewall firewall add rule "
        f"name=\"{rule_name}\" dir=in action=allow "
        f"protocol={proto} localport={port}"
    )

    # Try running via PowerShell (needs admin)
    for cmd in [portproxy_cmd, firewall_cmd]:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "access" in result.stderr.lower():
            rprint(f"[red]Elevation required.[/red] Run these in an admin PowerShell:\n")
            rprint(f"  {portproxy_cmd}")
            rprint(f"  {firewall_cmd}")

            # Write helper script
            script_path = config.DEVMESH_DIR / f"expose-{port}.ps1"
            script_path.write_text(f"{portproxy_cmd}\n{firewall_cmd}\n")
            rprint(f"\n[dim]Or run the script: powershell.exe -ExecutionPolicy Bypass -File {script_path}[/dim]")
            return
        elif result.returncode != 0:
            rprint(f"[red]Failed:[/red] {result.stderr.strip()}")
            return

    # Track in config
    if not any(r.local_port == port and r.proto == proto for r in cfg.port_rules):
        cfg.port_rules.append(PortRule(local_port=port, proto=proto))
        config.save(cfg)

    rprint(f"[green]Port {port}/{proto} exposed[/green] (WSL IP: {wsl_ip})")


def unexpose_port(cfg: Config, port: int, proto: str = "tcp") -> None:
    """Remove a port forward."""
    if detect_os() != "wsl2":
        rprint("[yellow]Port forwarding via netsh is only available on WSL2.[/yellow]")
        return

    rule_name = _firewall_rule_name(port, proto)

    delete_proxy = (
        f"netsh interface portproxy delete v4tov4 "
        f"listenport={port} listenaddress=0.0.0.0"
    )
    delete_fw = (
        f"netsh advfirewall firewall delete rule name=\"{rule_name}\""
    )

    for cmd in [delete_proxy, delete_fw]:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True,
        )
        if result.returncode != 0 and "access" in result.stderr.lower():
            rprint(f"[red]Elevation required.[/red] Run in admin PowerShell:\n")
            rprint(f"  {delete_proxy}")
            rprint(f"  {delete_fw}")
            return

    # Remove from config
    cfg.port_rules = [r for r in cfg.port_rules if not (r.local_port == port and r.proto == proto)]
    config.save(cfg)

    rprint(f"[green]Port {port}/{proto} unexposed[/green]")


def show_portproxy_rules() -> None:
    """Show current netsh portproxy rules (WSL2 only)."""
    if detect_os() != "wsl2":
        rprint("[yellow]netsh portproxy is only available on WSL2.[/yellow]")
        return

    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "netsh interface portproxy show v4tov4"],
        capture_output=True, text=True,
    )
    if result.stdout.strip():
        print(result.stdout)
    else:
        rprint("[dim]No active port forwards[/dim]")
