# devmesh
CLI tool for connecting dev environments across WSL2, macOS, and Linux — manages SSH keys, Tailscale mesh networking, port forwarding, and remote command execution.
=======

A CLI tool for connecting development environments across WSL2, macOS, and Linux machines. Manages SSH keys, Tailscale mesh networking, port forwarding, and remote command execution from a single interface.

## Install

Requires Python 3.11+.

```bash
cd ~/git/devmesh
pip install -e .
```

## Quick Start

```bash
# Initialize this machine
devmesh init

# Add a remote machine
devmesh node add workshop --ip 100.64.0.2 --os linux

# Push your SSH key to it
devmesh ssh push-key workshop

# Run a command on it
devmesh run workshop -- uname -a
```

## Commands

| Command | Description |
|---------|-------------|
| `devmesh init` | First-time node setup (detects platform, generates SSH key) |
| `devmesh status` | Overview of this node and all remotes |
| `devmesh node list\|add\|remove\|ping` | Manage remote nodes |
| `devmesh ssh keygen\|push-key\|write-config` | SSH key and config management |
| `devmesh ports list\|expose\|unexpose\|status` | WSL2 port forwarding via netsh |
| `devmesh tailscale status\|install` | Tailscale integration |
| `devmesh run <node\|--all> -- <cmd>` | Remote command execution via SSH |

## How It Works

- **Tailscale** is the primary networking layer — stable IPs, NAT traversal, no port forwarding needed
- **netsh portproxy** is a WSL2-only fallback for exposing ports to the LAN without Tailscale
- **SSH keys** are stored separately in `~/.devmesh/` to avoid conflicts with GitHub keys
- **Config** lives at `~/.devmesh/config.toml`

See [docs/guide.md](docs/guide.md) for detailed usage, configuration reference, and platform-specific notes.
