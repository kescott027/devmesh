# devmesh User Guide

## Table of Contents

- [Setup](#setup)
- [Node Management](#node-management)
- [SSH](#ssh)
- [Port Forwarding (WSL2)](#port-forwarding-wsl2)
- [Tailscale](#tailscale)
- [Remote Execution](#remote-execution)
- [Configuration Reference](#configuration-reference)
- [Platform Notes](#platform-notes)

---

## Setup

### Install

```bash
cd ~/git/devmesh
pip install -e .
```

### Initialize

Run on each machine that will participate in the mesh:

```bash
devmesh init
```

This will:
1. Prompt for a node name (defaults to hostname)
2. Detect your platform (WSL2, macOS, or Linux)
3. Check for Tailscale and record its IP if present
4. Generate an ed25519 SSH key at `~/.devmesh/id_ed25519`
5. Check if the SSH daemon is running (Linux/WSL2)
6. Write `~/.devmesh/config.toml`

### Check status

```bash
devmesh status
```

Shows this node's config, Tailscale state, forwarded ports, and a table of all remote nodes.

---

## Node Management

### Add a node

```bash
devmesh node add <name> --ip <ip> [--os wsl2|mac|linux] [--ssh-user USER] [--ssh-port PORT] [--lan-ip IP]
```

The `--ip` value is auto-classified: IPs starting with `100.` are treated as Tailscale IPs, everything else as LAN IPs. To specify both:

```bash
devmesh node add workshop --ip 100.64.0.2 --lan-ip 192.168.1.50 --os linux
```

Adding a node automatically updates `~/.ssh/config` with a `devmesh-<name>` host alias.

### List nodes

```bash
devmesh node list
```

### Remove a node

```bash
devmesh node remove <name>
```

Also removes the corresponding `~/.ssh/config` entry.

### Ping / health check

```bash
devmesh node ping workshop
devmesh node ping --all
```

Performs a TCP connect to the SSH port (3-second timeout). If the Tailscale IP is unreachable, falls back to the LAN IP.

---

## SSH

devmesh manages its own SSH key pair, separate from any GitHub keys you may have.

### Generate key

```bash
devmesh ssh keygen
```

Creates `~/.devmesh/id_ed25519` and `~/.devmesh/id_ed25519.pub`. Skips if the key already exists. This is also run automatically by `devmesh init`.

### Push key to a remote node

```bash
devmesh ssh push-key workshop
devmesh ssh push-key --all
```

SSHs into the target and appends the public key to `~/.ssh/authorized_keys` (idempotent — won't duplicate). You'll need password access or an existing key for the first push.

### Write SSH config

```bash
devmesh ssh write-config
```

Writes a managed block into `~/.ssh/config`:

```
# --- BEGIN devmesh ---
Host devmesh-workshop
    HostName 100.64.0.2
    User tecthulhu
    Port 22
    IdentityFile /home/tecthulhu/.devmesh/id_ed25519
    StrictHostKeyChecking accept-new
# --- END devmesh ---
```

Everything outside the `BEGIN`/`END` markers is left untouched. Your GitHub host entries, personal aliases, etc. are safe. This is also run automatically when you `node add` or `node remove`.

After this, you can SSH directly:

```bash
ssh devmesh-workshop
```

---

## Port Forwarding (WSL2)

WSL2 runs in a NAT'd VM — services listening inside WSL aren't reachable from other machines on the LAN by default. devmesh automates the `netsh` portproxy and firewall rules to fix this.

> **If you have Tailscale running inside WSL2, you don't need port forwarding.** Services are directly reachable at your Tailscale IP. devmesh will remind you of this.

### List listening ports

```bash
devmesh ports list
```

Parses `ss -tlnp` to show all listening TCP ports and their processes.

### Expose a port

```bash
devmesh ports expose 8080
```

This runs (via PowerShell from WSL):

```
netsh interface portproxy add v4tov4 listenport=8080 listenaddress=0.0.0.0 connectport=8080 connectaddress=<WSL_IP>
netsh advfirewall firewall add rule name="devmesh-8080-tcp" dir=in action=allow protocol=tcp localport=8080
```

**If elevation is required** (the normal case), devmesh prints the exact commands to run in an admin PowerShell and also writes a helper script at `~/.devmesh/expose-8080.ps1`.

The rule is idempotent — re-running `expose` on an already-forwarded port is a no-op.

### Unexpose a port

```bash
devmesh ports unexpose 8080
```

Removes the portproxy and firewall rules.

### Show active forwards

```bash
devmesh ports status
```

Runs `netsh interface portproxy show v4tov4` and displays the output.

### Important: WSL2 IP changes on reboot

The WSL2 VM gets a new IP each time it restarts. If you reboot, re-run `devmesh ports expose <port>` to update the forwarding rule.

---

## Tailscale

Tailscale is the recommended networking layer. It gives each machine a stable `100.x.y.z` IP, handles NAT traversal, and removes the need for port forwarding.

### Check status

```bash
devmesh tailscale status
```

Shows your Tailscale identity, IP, and a table of all peers on your tailnet.

### Install guide

```bash
devmesh tailscale install
```

Prints platform-appropriate instructions:

| Platform | Method |
|----------|--------|
| WSL2 / Linux | `curl -fsSL https://tailscale.com/install.sh \| sh` then `sudo tailscale up` |
| macOS | `brew install --cask tailscale` or download from tailscale.com |

After installing Tailscale on a new node, run `devmesh init` again (or edit `~/.devmesh/config.toml`) to pick up the Tailscale IP.

---

## Remote Execution

Run commands on remote nodes over SSH. Uses the `devmesh-<name>` host aliases from `~/.ssh/config`.

### Single node

```bash
devmesh run workshop -- uname -a
devmesh run workshop -- docker ps
```

Stdin/stdout/stderr pass through directly. Exit code is forwarded.

### All nodes in parallel

```bash
devmesh run --all -- df -h /
devmesh run --all -- systemctl is-active docker
```

Output is prefixed with the node name:

```
workshop | /dev/sda1  50G  12G  38G  24% /
macbook  | /dev/disk1 500G 200G 300G  40% /
```

Execution uses a thread pool — all nodes run concurrently with a 30-second timeout per node.

---

## Configuration Reference

Config file: `~/.devmesh/config.toml`

```toml
[self]
name = "tecthulhu-wsl"          # this node's name
os = "wsl2"                     # detected platform: wsl2, mac, linux
ssh_key = "~/.devmesh/id_ed25519"
ssh_port = 22

[tailscale]
installed = true                # auto-detected
ip = "100.64.0.1"              # auto-detected

[[ports.rules]]                 # tracked port forwards
local_port = 8080
proto = "tcp"
description = "dev server"

[nodes.workshop]                # one section per remote node
os = "linux"
tailscale_ip = "100.64.0.2"
lan_ip = "192.168.1.50"
ssh_port = 22
ssh_user = "tecthulhu"

[nodes.macbook]
os = "mac"
tailscale_ip = "100.64.0.3"
lan_ip = ""
ssh_port = 22
ssh_user = "tecthulhu"
```

### File layout

```
~/.devmesh/
├── config.toml          # main config
├── id_ed25519           # private key
├── id_ed25519.pub       # public key
└── expose-8080.ps1      # generated helper scripts (WSL2 only)
```

---

## Platform Notes

### WSL2

- Platform detected via `/proc/version` containing "microsoft"
- Port forwarding uses `netsh` via `powershell.exe` from inside WSL
- WSL2 IP (`eth0`) changes on reboot — port forwards need refreshing
- If Tailscale is installed inside WSL2, port forwarding is unnecessary
- `sshd` may not be running by default — `devmesh init` checks and tells you how to enable it

### macOS

- No port forwarding support (not needed — macOS isn't NAT'd)
- Tailscale installs as a system app via Homebrew or direct download
- SSH daemon can be enabled in System Settings > General > Sharing > Remote Login

### Linux

- Straightforward — same as WSL2 minus the `netsh` port forwarding
- `devmesh init` checks for `sshd` and suggests `sudo systemctl enable --now ssh`
