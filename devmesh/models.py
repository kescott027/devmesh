from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    name: str
    os: str  # "wsl2", "mac", "linux"
    ssh_user: str = ""
    ssh_port: int = 22
    tailscale_ip: str = ""
    lan_ip: str = ""


@dataclass
class PortRule:
    local_port: int
    proto: str = "tcp"
    description: str = ""


@dataclass
class SelfNode:
    name: str = ""
    os: str = ""
    ssh_key: str = "~/.devmesh/id_ed25519"
    ssh_port: int = 22


@dataclass
class TailscaleInfo:
    installed: bool = False
    ip: str = ""


@dataclass
class Config:
    self_node: SelfNode = field(default_factory=SelfNode)
    tailscale: TailscaleInfo = field(default_factory=TailscaleInfo)
    nodes: dict[str, Node] = field(default_factory=dict)
    port_rules: list[PortRule] = field(default_factory=list)
