from __future__ import annotations

import socket
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.table import Table

from devmesh import config, mesh, ports, remote, ssh
from devmesh.models import Node
from devmesh.platform_detect import detect_os

app = typer.Typer(help="Development environment mesh tool.", no_args_is_help=True)
node_app = typer.Typer(help="Manage remote nodes.", no_args_is_help=True)
ssh_app = typer.Typer(help="SSH key and config management.", no_args_is_help=True)
ports_app = typer.Typer(help="Port forwarding (WSL2).", no_args_is_help=True)
ts_app = typer.Typer(help="Tailscale integration.", no_args_is_help=True)

app.add_typer(node_app, name="node")
app.add_typer(ssh_app, name="ssh")
app.add_typer(ports_app, name="ports")
app.add_typer(ts_app, name="tailscale")


# ── Top-level commands ──────────────────────────────────────────────


@app.command()
def init():
    """First-time node setup."""
    cfg = config.load()
    os_type = detect_os()

    if cfg.self_node.name:
        rprint(f"[yellow]Already initialized as '{cfg.self_node.name}' ({cfg.self_node.os})[/yellow]")
        rprint("[dim]Edit ~/.devmesh/config.toml to change settings.[/dim]")
        return

    hostname = socket.gethostname()
    name = typer.prompt("Node name", default=hostname)
    cfg.self_node.name = name
    cfg.self_node.os = os_type

    # Detect Tailscale
    mesh.detect_tailscale(cfg)
    if cfg.tailscale.installed:
        rprint(f"[green]Tailscale detected:[/green] {cfg.tailscale.ip}")
    else:
        rprint("[dim]Tailscale not detected. Run 'devmesh tailscale install' for setup guide.[/dim]")

    # Generate SSH key
    ssh.keygen(cfg)

    # Check sshd
    if os_type in ("wsl2", "linux"):
        if ssh.check_sshd():
            rprint("[green]SSH daemon is running[/green]")
        else:
            rprint("[yellow]SSH daemon is not running.[/yellow]")
            rprint("  sudo systemctl enable --now ssh")

    config.save(cfg)
    rprint(f"\n[green]Initialized '{name}'[/green] (platform: {os_type})")
    rprint(f"Config: {config.CONFIG_PATH}")


@app.command()
def status():
    """Overview of this node and all remotes."""
    cfg = config.load()

    if not cfg.self_node.name:
        rprint("[red]Not initialized. Run 'devmesh init' first.[/red]")
        raise typer.Exit(1)

    # Self info
    rprint(f"[bold]Node:[/bold] {cfg.self_node.name} ({cfg.self_node.os})")
    if cfg.tailscale.installed:
        rprint(f"[bold]Tailscale:[/bold] {cfg.tailscale.ip}")
    else:
        rprint("[bold]Tailscale:[/bold] [dim]not installed[/dim]")

    # Port rules
    if cfg.port_rules:
        rprint(f"[bold]Forwarded ports:[/bold] {', '.join(str(r.local_port) for r in cfg.port_rules)}")

    # Nodes table
    if cfg.nodes:
        rprint()
        table = Table(title="Remote Nodes")
        table.add_column("Name")
        table.add_column("OS")
        table.add_column("Tailscale IP")
        table.add_column("LAN IP")
        table.add_column("SSH")
        for name, node in cfg.nodes.items():
            table.add_row(
                name,
                node.os,
                node.tailscale_ip or "-",
                node.lan_ip or "-",
                f"{node.ssh_user or 'tecthulhu'}@:{node.ssh_port}",
            )
        rprint(table)
    else:
        rprint("\n[dim]No remote nodes configured. Use 'devmesh node add' to add one.[/dim]")


# ── Node commands ───────────────────────────────────────────────────


@node_app.command("list")
def node_list():
    """List configured remote nodes."""
    cfg = config.load()
    if not cfg.nodes:
        rprint("[dim]No nodes configured.[/dim]")
        return
    table = Table()
    table.add_column("Name")
    table.add_column("OS")
    table.add_column("Tailscale IP")
    table.add_column("LAN IP")
    for name, node in cfg.nodes.items():
        table.add_row(name, node.os, node.tailscale_ip or "-", node.lan_ip or "-")
    rprint(table)


@node_app.command("add")
def node_add(
    name: str,
    ip: Annotated[str, typer.Option(help="IP address (Tailscale or LAN)")],
    os: Annotated[str, typer.Option(help="OS type: wsl2, mac, linux")] = "linux",
    ssh_user: str = "tecthulhu",
    ssh_port: int = 22,
    lan_ip: str = "",
):
    """Add a remote node."""
    cfg = config.load()
    if name in cfg.nodes:
        rprint(f"[yellow]Node '{name}' already exists. Remove it first to update.[/yellow]")
        raise typer.Exit(1)

    # If ip looks like a Tailscale IP (100.x.x.x), set tailscale_ip
    tailscale_ip = ip if ip.startswith("100.") else ""
    if not tailscale_ip:
        lan_ip = lan_ip or ip

    cfg.nodes[name] = Node(
        name=name,
        os=os,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        tailscale_ip=tailscale_ip,
        lan_ip=lan_ip,
    )
    config.save(cfg)
    ssh.write_ssh_config(cfg)
    rprint(f"[green]Added node '{name}'[/green]")


@node_app.command("remove")
def node_remove(name: str):
    """Remove a remote node."""
    cfg = config.load()
    if name not in cfg.nodes:
        rprint(f"[red]Unknown node: {name}[/red]")
        raise typer.Exit(1)
    del cfg.nodes[name]
    config.save(cfg)
    ssh.write_ssh_config(cfg)
    rprint(f"[green]Removed node '{name}'[/green]")


@node_app.command("ping")
def node_ping(
    name: Optional[str] = typer.Argument(None),
    all_nodes: Annotated[bool, typer.Option("--all")] = False,
):
    """Check connectivity to a node (TCP connect to SSH port)."""
    cfg = config.load()
    targets = list(cfg.nodes.keys()) if all_nodes else ([name] if name else [])
    if not targets:
        rprint("[red]Specify a node name or --all[/red]")
        raise typer.Exit(1)

    for t in targets:
        node = cfg.nodes.get(t)
        if not node:
            rprint(f"[red]Unknown node: {t}[/red]")
            continue
        host = node.tailscale_ip or node.lan_ip
        if not host:
            rprint(f"[yellow]{t}:[/yellow] no IP configured")
            continue
        try:
            sock = socket.create_connection((host, node.ssh_port), timeout=3)
            sock.close()
            rprint(f"[green]{t}:[/green] reachable ({host}:{node.ssh_port})")
        except (OSError, TimeoutError):
            # Try LAN fallback if we tried Tailscale first
            if node.tailscale_ip and node.lan_ip:
                try:
                    sock = socket.create_connection((node.lan_ip, node.ssh_port), timeout=3)
                    sock.close()
                    rprint(f"[yellow]{t}:[/yellow] reachable via LAN only ({node.lan_ip}:{node.ssh_port})")
                    continue
                except (OSError, TimeoutError):
                    pass
            rprint(f"[red]{t}:[/red] unreachable")


# ── SSH commands ────────────────────────────────────────────────────


@ssh_app.command("keygen")
def ssh_keygen():
    """Generate a devmesh SSH key pair."""
    cfg = config.load()
    ssh.keygen(cfg)


@ssh_app.command("push-key")
def ssh_push_key(
    node_name: Optional[str] = typer.Argument(None),
    all_nodes: Annotated[bool, typer.Option("--all")] = False,
):
    """Push the devmesh public key to a remote node."""
    cfg = config.load()
    targets = list(cfg.nodes.keys()) if all_nodes else ([node_name] if node_name else [])
    if not targets:
        rprint("[red]Specify a node name or --all[/red]")
        raise typer.Exit(1)
    for t in targets:
        ssh.push_key(cfg, t)


@ssh_app.command("write-config")
def ssh_write_config():
    """Write devmesh entries to ~/.ssh/config."""
    cfg = config.load()
    ssh.write_ssh_config(cfg)


# ── Ports commands ──────────────────────────────────────────────────


@ports_app.command("list")
def ports_list():
    """Show listening TCP ports on this machine."""
    listening = ports.list_listening_ports()
    if not listening:
        rprint("[dim]No listening TCP ports found.[/dim]")
        return
    table = Table(title="Listening Ports")
    table.add_column("Port", justify="right")
    table.add_column("Address")
    table.add_column("Process")
    for p in sorted(listening, key=lambda x: x["port"]):
        table.add_row(str(p["port"]), p["address"], p["process"])
    rprint(table)


@ports_app.command("expose")
def ports_expose(port: int):
    """Forward a WSL2 port to the Windows host LAN."""
    cfg = config.load()
    ports.expose_port(cfg, port)


@ports_app.command("unexpose")
def ports_unexpose(port: int):
    """Remove a port forward."""
    cfg = config.load()
    ports.unexpose_port(cfg, port)


@ports_app.command("status")
def ports_status():
    """Show active netsh port forwards."""
    ports.show_portproxy_rules()


# ── Tailscale commands ──────────────────────────────────────────────


@ts_app.command("status")
def tailscale_status():
    """Show Tailscale network status."""
    data = mesh.tailscale_status()
    if not data:
        rprint("[yellow]Tailscale is not running or not installed.[/yellow]")
        rprint("[dim]Run 'devmesh tailscale install' for setup instructions.[/dim]")
        return

    self_node = data.get("Self", {})
    rprint(f"[bold]Tailscale:[/bold] {self_node.get('HostName', '?')}")
    rprint(f"  IP: {', '.join(self_node.get('TailscaleIPs', []))}")
    rprint(f"  Online: {self_node.get('Online', False)}")

    peers = data.get("Peer", {})
    if peers:
        rprint(f"\n[bold]Peers ({len(peers)}):[/bold]")
        table = Table()
        table.add_column("Name")
        table.add_column("IP")
        table.add_column("OS")
        table.add_column("Online")
        for _, peer in peers.items():
            ips = peer.get("TailscaleIPs", [])
            table.add_row(
                peer.get("HostName", "?"),
                ips[0] if ips else "-",
                peer.get("OS", "?"),
                "[green]yes[/green]" if peer.get("Online") else "[red]no[/red]",
            )
        rprint(table)


@ts_app.command("install")
def tailscale_install():
    """Show platform-specific Tailscale installation guide."""
    cfg = config.load()
    os_type = cfg.self_node.os or detect_os()
    mesh.print_install_guide(os_type)


# ── Run command ─────────────────────────────────────────────────────


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    node_name: Optional[str] = typer.Argument(None),
    all_nodes: Annotated[bool, typer.Option("--all")] = False,
):
    """Execute a command on remote node(s) via SSH."""
    cfg = config.load()
    targets = list(cfg.nodes.keys()) if all_nodes else ([node_name] if node_name else [])
    if not targets:
        rprint("[red]Specify a node name or --all[/red]")
        raise typer.Exit(1)

    command = ctx.args
    if not command:
        rprint("[red]No command specified. Use: devmesh run <node> -- <command>[/red]")
        raise typer.Exit(1)

    remote.run_command(cfg, targets, command)
