from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich import print as rprint

from devmesh.models import Config, Node


def run_on_node(node_name: str, node: Node, command: list[str]) -> tuple[str, int, str, str]:
    """Run a command on a remote node via SSH. Returns (name, returncode, stdout, stderr)."""
    host = f"devmesh-{node_name}"  # Uses SSH config alias
    result = subprocess.run(
        ["ssh", host, "--", *command],
        capture_output=True, text=True, timeout=30,
    )
    return node_name, result.returncode, result.stdout, result.stderr


def run_command(cfg: Config, targets: list[str], command: list[str]) -> None:
    """Run a command on one or more nodes."""
    nodes = {}
    for name in targets:
        node = cfg.nodes.get(name)
        if not node:
            rprint(f"[red]Unknown node:[/red] {name}")
            raise SystemExit(1)
        nodes[name] = node

    if len(nodes) == 1:
        name, node = next(iter(nodes.items()))
        try:
            _, rc, stdout, stderr = run_on_node(name, node, command)
            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="")
            raise SystemExit(rc)
        except subprocess.TimeoutExpired:
            rprint(f"[red]Timeout connecting to {name}[/red]")
            raise SystemExit(1)
    else:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=len(nodes)) as pool:
            futures = {
                pool.submit(run_on_node, name, node, command): name
                for name, node in nodes.items()
            }
            for future in as_completed(futures):
                try:
                    name, rc, stdout, stderr = future.result(timeout=30)
                    prefix = f"[bold cyan]{name}[/bold cyan]"
                    if stdout:
                        for line in stdout.splitlines():
                            rprint(f"{prefix} | {line}")
                    if stderr:
                        for line in stderr.splitlines():
                            rprint(f"{prefix} | [red]{line}[/red]")
                    if rc != 0:
                        rprint(f"{prefix} | [red]exit {rc}[/red]")
                except subprocess.TimeoutExpired:
                    rprint(f"[red]Timeout connecting to {futures[future]}[/red]")
