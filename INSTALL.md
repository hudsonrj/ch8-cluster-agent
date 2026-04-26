# CH8 — Installation Guide

Complete guide for deploying the CH8 distributed agent mesh.
Architecture: **1 Control Server** + **N Agent Nodes**.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Part 1 — Control Server](#part-1--control-server)
4. [Part 2 — Agent Node](#part-2--agent-node)
5. [Networking](#networking)
6. [Post-Install](#post-install)
7. [Troubleshooting](#troubleshooting)

---

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    CH8 Architecture                      │
│                                                          │
│  ┌──────────────┐       ┌──────────────┐                │
│  │ Control       │       │  Node A       │                │
│  │ Server        │◄─────►│  (ch8 agent)  │                │
│  │ (dashboard +  │       │  orchestrator │                │
│  │  API)         │       │  monitor      │                │
│  └──────┬───────┘       └──────────────┘                │
│         │                                                │
│         │  Tailscale / LAN / VPN                         │
│         │                                                │
│  ┌──────┴───────┐       ┌──────────────┐                │
│  │  Node B       │       │  Node C       │                │
│  │  (ch8 agent)  │◄─────►│  (ch8 agent)  │                │
│  │  + Ollama     │       │  + GPU        │                │
│  └──────────────┘       └──────────────┘                │
└─────────────────────────────────────────────────────────┘
```

**Control Server** — Manages the mesh. Runs the web dashboard, API, and coordinates all nodes. Deployed as a Docker container.

**Agent Node** — Any machine running the CH8 agent. Auto-detects capabilities (Ollama, GPU, Docker, etc.), runs monitoring agents, and communicates with peers.

---

## Prerequisites

| Component | Control Server | Agent Node |
|-----------|---------------|------------|
| OS | Linux (Ubuntu 20.04+, Debian 11+) | Linux, macOS |
| Python | — (runs in Docker) | 3.10+ |
| Docker | Required | Optional (for monitoring) |
| Git | Required | Required |
| Network | Public IP or Tailscale | Tailscale, LAN, or VPN |

---

## Part 1 — Control Server

### Automated Install

```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-control.sh | bash
```

The script will:
1. Check Docker, Docker Compose, Git
2. Clone the repository
3. Configure domain and nginx (optional)
4. Build and start the Docker container
5. Generate a bootstrap token for connecting nodes

### Manual Install (Step by Step)

#### 1.1 Clone the repository

```bash
git clone https://github.com/hudsonrj/ch8-cluster-agent.git /data/ch8-control
cd /data/ch8-control
```

#### 1.2 Configure the domain

Edit `docker-compose.yml`:

```yaml
services:
  control-server:
    build: .
    container_name: ch8-control
    ports:
      - "8081:8000"
    environment:
      - CH8_CONTROL_BASE_URL=https://your-domain.com
    volumes:
      - ch8-control-data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  ch8-control-data:
```

#### 1.3 Build and start

```bash
docker compose build
docker compose up -d
```

#### 1.4 Verify

```bash
curl http://localhost:8081/health
# {"status":"ok","ts":...,"total_nodes":0,"online_nodes":0,...}
```

#### 1.5 Configure reverse proxy (production)

Nginx config for HTTPS:

```nginx
server {
    listen 80;
    server_name control.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support (for chat streaming)
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ch8-control /etc/nginx/sites-enabled/
sudo certbot --nginx -d control.your-domain.com
sudo systemctl reload nginx
```

#### 1.6 Generate bootstrap token

```bash
# From the control server machine (localhost only):
curl -X POST "http://localhost:8081/api/admin/bootstrap?label=bootstrap&ttl_hours=8760"
```

Save the returned `token` value — you'll need it to connect nodes.

---

## Part 2 — Agent Node

### Automated Install

```bash
# Basic install:
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-node.sh | bash

# With token (non-interactive):
curl -fsSL ... | bash -s -- --token tk_your_token_here

# With all options:
curl -fsSL ... | bash -s -- \
    --token tk_xxx \
    --control-url https://control.your-domain.com \
    --advertise-addr 10.0.0.5
```

### Manual Install (Step by Step)

#### 2.1 Install Python 3.10+

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git

# macOS
brew install python@3.12 git
```

#### 2.2 Clone the repository

```bash
git clone https://github.com/hudsonrj/ch8-cluster-agent.git /data/ch8-agent
cd /data/ch8-agent
```

#### 2.3 Install Python dependencies

```bash
pip install --break-system-packages httpx psutil fastapi uvicorn pydantic
```

#### 2.4 Configure the control server URL

```bash
mkdir -p ~/.config/ch8
export CH8_CONTROL_URL=https://control.your-domain.com
```

To make it permanent:

```bash
echo 'export CH8_CONTROL_URL=https://control.your-domain.com' >> ~/.bashrc
```

#### 2.5 Add CH8 to PATH

```bash
chmod +x /data/ch8-agent/ch8
echo 'export PATH="$PATH:/data/ch8-agent"' >> ~/.bashrc
source ~/.bashrc
```

#### 2.6 Connect to the network

```bash
ch8 up --token tk_your_token_here
```

Expected output:

```
✓ Tailscale  100.x.x.x
Starting CH8 Connect...
✓ Agent 'orchestrator' started (PID 12345)
✓ Agent 'server-monitor' started (PID 12346)
✓ CH8 Connect is up!
  Peers online: 0

Run ch8 nodes to see your cluster.
```

#### 2.7 Verify

```bash
ch8 nodes
```

Check the dashboard at `https://control.your-domain.com` — your node should appear within seconds.

---

## Networking

CH8 nodes need to communicate with:
1. **Control server** — HTTPS (port 443) for registration, heartbeats, peer discovery
2. **Other nodes** — Direct TCP (ports 7878-7879) for peer-to-peer communication and chat

### Option A: Tailscale (Recommended)

Tailscale creates a secure mesh VPN. Each machine gets a `100.x.x.x` address reachable from any other Tailscale node, regardless of NAT or firewall.

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Connect to your Tailscale network
sudo tailscale up

# Verify
tailscale ip --4
# 100.64.0.1
```

**Advantages:**
- Works across NAT, firewalls, different networks
- Encrypted WireGuard tunnel
- Zero configuration for node-to-node communication
- Automatic key rotation

**When to use:** Nodes on different networks, cloud + on-premises, behind NAT.

### Option B: Same LAN

If all nodes are on the same local network, no extra configuration is needed. The daemon auto-detects the LAN IP.

```bash
# Just connect — it works:
ch8 up --token tk_xxx
```

**When to use:** All nodes on the same office/home network or VLAN.

### Option C: WireGuard / VPN

If you already have a WireGuard or OpenVPN setup, use the VPN IP for each node:

```bash
# Set the VPN IP as the advertise address:
export CH8_ADVERTISE_ADDR=10.0.0.5
ch8 up --token tk_xxx
```

Or in the install script:

```bash
bash install-node.sh --token tk_xxx --advertise-addr 10.0.0.5
```

**When to use:** Existing VPN infrastructure, corporate networks.

### Option D: Public IP + Firewall

For nodes with public IPs (cloud VMs), open ports 7878-7879 and use the public IP:

```bash
# Open ports (example: Ubuntu with UFW)
sudo ufw allow 7878/tcp
sudo ufw allow 7879/tcp

# Set the public IP
export CH8_ADVERTISE_ADDR=203.0.113.50
ch8 up --token tk_xxx
```

**When to use:** Cloud VMs (AWS, GCP, Azure, etc.) without VPN.

### Network Priority

The daemon automatically selects the best address in this order:

1. `CH8_ADVERTISE_ADDR` environment variable (explicit override)
2. Tailscale IP (`100.x.x.x`) if Tailscale is connected
3. LAN IP (auto-detected, fallback)

### Ports Reference

| Port | Protocol | Used By | Direction |
|------|----------|---------|-----------|
| 443 | HTTPS | Control server | Node → Control |
| 8081 | HTTP | Control server (Docker) | Internal |
| 7878 | TCP | CH8 daemon (peer) | Node ↔ Node |
| 7879 | TCP | Orchestrator agent | Node ↔ Node |
| 11434 | TCP | Ollama API | Local only |

---

## Post-Install

### Managing nodes

```bash
# Connect this node
ch8 up --token tk_xxx

# Disconnect
ch8 down

# List all nodes
ch8 nodes

# Create a token for other nodes
ch8 token create

# Show help
ch8 help
```

### What runs on each node

When you run `ch8 up`, three processes start:

| Process | Description | Port |
|---------|-------------|------|
| `connect.daemon` | Heartbeat, peer discovery, metrics collection | 7878 |
| `orchestrator.py` | Default AI agent — chat interface via dashboard | 7879 |
| `server_monitor.py` | Security scanning, resource monitoring, alerts | — |

### Agents on each node

- **Orchestrator** — The primary agent. Users interact with it via the dashboard chat. It has live system context (CPU, containers, peers, models) and answers questions using the local Ollama model.

- **Server Monitor** — Runs security scans every 60s, resource checks every 15s. Detects:
  - Cryptominers and suspicious processes
  - Publicly exposed database ports
  - Weak passwords on containers
  - Resource threshold breaches
  - Trend-based predictions (e.g., "disk will be full in 2 hours")

### Adding Ollama (AI capabilities)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen2.5:1.5b    # lightweight, 1GB
ollama pull gemma3:4b        # balanced, 3GB
ollama pull llama3.2         # full-featured, 4GB

# CH8 auto-detects Ollama models — just restart:
ch8 down && ch8 up --token tk_xxx
```

### Dashboard

Access the web dashboard at your control server URL:

- **Node cards** — Real-time CPU, memory, disk metrics for each node
- **Agent status** — Click an agent to see alerts, security findings, predictions
- **Services** — Click the services badge to see Docker containers and ports
- **Chat** — Click the chat icon (on nodes with Ollama) to interact with the orchestrator

---

## Troubleshooting

### Node not appearing in dashboard

```bash
# Check daemon is running:
ps aux | grep connect.daemon

# Check authentication:
cat ~/.config/ch8/auth.json

# Check control server is reachable:
curl -v https://control.your-domain.com/health

# Restart:
ch8 down && ch8 up --token tk_xxx
```

### "Not authenticated" error

```bash
# Re-authenticate with token:
rm ~/.config/ch8/auth.json
ch8 up --token tk_xxx
```

### Nodes can't reach each other

```bash
# Check if Tailscale is connected:
tailscale status

# Verify the advertised address:
cat ~/.config/ch8/state.json | python3 -m json.tool

# Test connectivity between nodes:
ping 100.x.x.x  # Tailscale IP of the other node
curl http://100.x.x.x:7879/health  # Orchestrator health
```

### Agents not showing in dashboard

```bash
# Check agents are running:
ps aux | grep -E "orchestrator|server_monitor"

# Check state file:
cat ~/.config/ch8/state.json | python3 -m json.tool | grep -A5 agents

# Restart agents:
ch8 down && ch8 up --token tk_xxx
```

### Control server container issues

```bash
# Check container status:
docker ps -a | grep ch8-control

# View logs:
docker logs ch8-control --tail 50

# Restart:
cd /data/ch8-control && docker compose restart

# Rebuild from scratch:
cd /data/ch8-control && docker compose down && docker compose build && docker compose up -d
```

### SSL certificate issues

```bash
# Renew certificate:
sudo certbot renew

# Check nginx config:
sudo nginx -t

# Reload nginx:
sudo systemctl reload nginx
```

---

## Quick Reference

### Install Control Server
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-control.sh | bash
```

### Install Node
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-node.sh | bash -s -- --token tk_xxx
```

### Key Paths

| Path | Description |
|------|-------------|
| `/data/ch8-agent/` | Agent installation |
| `/data/ch8-control/` | Control server installation |
| `~/.config/ch8/auth.json` | Node credentials |
| `~/.config/ch8/state.json` | Node state (agents, peers) |
| `~/.config/ch8/daemon.pid` | Daemon PID file |
| `~/.config/ch8/env` | Environment config |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CH8_CONTROL_URL` | `https://control.ch8ai.com.br` | Control server URL |
| `CH8_ADVERTISE_ADDR` | auto-detect | IP to advertise to peers |
| `CH8_PORT` | `7878` | Daemon listen port |
| `CH8_HEARTBEAT` | `5` | Heartbeat interval (seconds) |
| `CH8_POLL_INTERVAL` | `30` | Peer discovery interval (seconds) |
| `CH8_MONITOR_INTERVAL` | `15` | Resource check interval (seconds) |
| `CH8_SECURITY_INTERVAL` | `60` | Security scan interval (seconds) |
