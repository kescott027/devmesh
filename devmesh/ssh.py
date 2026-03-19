from __future__ import annotations

import subprocess
from pathlib import Path

from rich import print as rprint

from devmesh import config
from devmesh.models import Config


def _key_path(cfg: Config) -> Path:
    return Path(cfg.self_node.ssh_key).expanduser()


def keygen(cfg: Config) -> None:
    """Generate an ed25519 key pair for devmesh."""
    key = _key_path(cfg)
    if key.exists():
        rprint(f"[yellow]Key already exists:[/yellow] {key}")
        return

    key.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key), "-N", "", "-C", f"devmesh@{cfg.self_node.name}"],
        check=True,
    )
    rprint(f"[green]Generated key:[/green] {key}")


def push_key(cfg: Config, node_name: str) -> None:
    """Copy the devmesh public key to a remote node's authorized_keys."""
    node = cfg.nodes.get(node_name)
    if not node:
        rprint(f"[red]Unknown node:[/red] {node_name}")
        raise SystemExit(1)

    pubkey = _key_path(cfg).with_suffix(".pub")
    if not pubkey.exists():
        rprint("[red]No public key found. Run 'devmesh ssh keygen' first.[/red]")
        raise SystemExit(1)

    pub_content = pubkey.read_text().strip()
    host = node.tailscale_ip or node.lan_ip
    user = node.ssh_user or "tecthulhu"

    if not host:
        rprint(f"[red]No IP configured for node {node_name}[/red]")
        raise SystemExit(1)

    # Append key if not already present
    cmd = (
        f"grep -qF '{pub_content}' ~/.ssh/authorized_keys 2>/dev/null "
        f"|| (mkdir -p ~/.ssh && chmod 700 ~/.ssh "
        f"&& echo '{pub_content}' >> ~/.ssh/authorized_keys "
        f"&& chmod 600 ~/.ssh/authorized_keys)"
    )
    subprocess.run(
        ["ssh", "-p", str(node.ssh_port), f"{user}@{host}", cmd],
        check=True,
    )
    rprint(f"[green]Key pushed to {node_name}[/green]")


def write_ssh_config(cfg: Config) -> None:
    """Write a managed block into ~/.ssh/config for all devmesh nodes."""
    ssh_config = Path.home() / ".ssh" / "config"
    ssh_config.parent.mkdir(parents=True, exist_ok=True)

    begin = "# --- BEGIN devmesh ---"
    end = "# --- END devmesh ---"

    # Build the managed block
    lines = [begin]
    key = _key_path(cfg)
    for name, node in cfg.nodes.items():
        host = node.tailscale_ip or node.lan_ip
        if not host:
            continue
        user = node.ssh_user or "tecthulhu"
        lines.append(f"Host devmesh-{name}")
        lines.append(f"    HostName {host}")
        lines.append(f"    User {user}")
        lines.append(f"    Port {node.ssh_port}")
        lines.append(f"    IdentityFile {key}")
        lines.append(f"    StrictHostKeyChecking accept-new")
        lines.append("")
    lines.append(end)
    block = "\n".join(lines) + "\n"

    if ssh_config.exists():
        content = ssh_config.read_text()
        if begin in content and end in content:
            # Replace existing block
            before = content[: content.index(begin)]
            after = content[content.index(end) + len(end) :]
            # Strip leading newline from after
            after = after.lstrip("\n")
            content = before + block + after
        else:
            content = content.rstrip("\n") + "\n\n" + block
    else:
        content = block

    ssh_config.write_text(content)
    rprint(f"[green]Updated[/green] {ssh_config}")


def check_sshd() -> bool:
    """Check if the SSH daemon is running."""
    result = subprocess.run(
        ["systemctl", "is-active", "ssh"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() == "active"
