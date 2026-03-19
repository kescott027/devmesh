from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from devmesh.models import Config, Node, PortRule, SelfNode, TailscaleInfo

DEVMESH_DIR = Path.home() / ".devmesh"
CONFIG_PATH = DEVMESH_DIR / "config.toml"


def ensure_dir() -> Path:
    DEVMESH_DIR.mkdir(parents=True, exist_ok=True)
    return DEVMESH_DIR


def load() -> Config:
    if not CONFIG_PATH.exists():
        return Config()

    raw = tomllib.loads(CONFIG_PATH.read_text())
    cfg = Config()

    if "self" in raw:
        s = raw["self"]
        cfg.self_node = SelfNode(
            name=s.get("name", ""),
            os=s.get("os", ""),
            ssh_key=s.get("ssh_key", "~/.devmesh/id_ed25519"),
            ssh_port=s.get("ssh_port", 22),
        )

    if "tailscale" in raw:
        t = raw["tailscale"]
        cfg.tailscale = TailscaleInfo(
            installed=t.get("installed", False),
            ip=t.get("ip", ""),
        )

    if "nodes" in raw:
        for name, data in raw["nodes"].items():
            cfg.nodes[name] = Node(
                name=name,
                os=data.get("os", "linux"),
                ssh_user=data.get("ssh_user", ""),
                ssh_port=data.get("ssh_port", 22),
                tailscale_ip=data.get("tailscale_ip", ""),
                lan_ip=data.get("lan_ip", ""),
            )

    if "ports" in raw and "rules" in raw["ports"]:
        for r in raw["ports"]["rules"]:
            cfg.port_rules.append(PortRule(
                local_port=r["local_port"],
                proto=r.get("proto", "tcp"),
                description=r.get("description", ""),
            ))

    return cfg


def save(cfg: Config) -> None:
    ensure_dir()

    doc: dict = {
        "self": {
            "name": cfg.self_node.name,
            "os": cfg.self_node.os,
            "ssh_key": cfg.self_node.ssh_key,
            "ssh_port": cfg.self_node.ssh_port,
        },
        "tailscale": {
            "installed": cfg.tailscale.installed,
            "ip": cfg.tailscale.ip,
        },
    }

    if cfg.port_rules:
        doc["ports"] = {
            "rules": [
                {"local_port": r.local_port, "proto": r.proto, "description": r.description}
                for r in cfg.port_rules
            ]
        }

    if cfg.nodes:
        doc["nodes"] = {}
        for name, node in cfg.nodes.items():
            doc["nodes"][name] = {
                "os": node.os,
                "ssh_user": node.ssh_user,
                "ssh_port": node.ssh_port,
                "tailscale_ip": node.tailscale_ip,
                "lan_ip": node.lan_ip,
            }

    CONFIG_PATH.write_text(tomli_w.dumps(doc))
