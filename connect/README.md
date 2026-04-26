# CH8 Connect

Tailscale-style auto-mesh for CH8 Agent nodes.

Install on any machine, authenticate once, and the node automatically discovers and joins your cluster — no manual IP configuration, no Redis setup required.

> **Tailscale is required** for nodes in different networks (different LANs, cloud providers, home networks) to communicate with each other. Install it first on every node you want to connect.

---

## Prerequisites

### 1. Tailscale (required for cross-network communication)

All nodes that need to talk to each other must be on the same Tailscale network.

```bash
# Linux / Raspberry Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# macOS
brew install tailscale
sudo tailscale up

# Windows
# Download from https://tailscale.com/download
```

After running `tailscale up`, your machine gets a stable `100.x.x.x` IP that works regardless of which network it's on. CH8 Connect automatically detects this IP and registers it with the control server.

> **Nodes on the same LAN** can communicate without Tailscale, but it is still strongly recommended for consistency and security.

---

## Quick Start

### Option 1 — Interactive login (recommended for first machine)

```bash
ch8 login       # opens browser for authentication
ch8 up          # daemon starts, node joins your network
ch8 nodes       # see all connected nodes
```

### Option 2 — Pre-auth token (headless, CI, Raspberry Pi, embedded devices)

```bash
# On an already-authenticated machine, generate a token:
ch8 token create

# On the new machine:
ch8 up --token tk_xxxxxxxxxxxxxxxx
ch8 nodes
```

---

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│                    CH8 Control Server                        │
│              (control.ch8ai.com.br)                         │
│                                                             │
│  POST /auth/device        ← device code login flow         │
│  POST /auth/preauth       ← token-based enrollment         │
│  POST /nodes/register     ← node registration              │
│  PUT  /nodes/:id/heartbeat← keepalive + metrics            │
│  GET  /nodes              ← peer discovery                 │
└───────────────┬──────────────────────────┬─────────────────┘
                │ register + heartbeat      │ register + heartbeat
                ▼                           ▼
        ┌───────────────┐           ┌───────────────┐
        │  Node A       │           │  Node B       │
        │  100.64.0.1   │◄─────────►│  100.64.0.2   │
        │  (your laptop)│  gRPC via │  (Raspberry Pi│
        └───────────────┘ Tailscale └───────────────┘
```

1. `ch8 up` checks that Tailscale is installed and running
2. The daemon reads the Tailscale IP (`tailscale ip --4`) and registers it with the control server
3. Polls the control server every 30s for the peer list — all peers have Tailscale IPs
4. Heartbeat every 15s keeps the node listed as online in the dashboard
5. On `ch8 down`, node is gracefully deregistered

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `ch8 login` | Authenticate via browser (device code) |
| `ch8 up` | Start daemon, connect to network |
| `ch8 up --token TOKEN` | Connect using pre-auth token |
| `ch8 down` | Disconnect (stops daemon) |
| `ch8 nodes` | List all online nodes in your network |
| `ch8 token create` | Generate a pre-auth token |
| `ch8 logout` | Remove credentials and disconnect |

---

## Dashboard

All connected nodes are visible at **https://control.ch8ai.com.br**

The dashboard shows each node's hostname, Tailscale IP, OS, active agents, CPU/memory/disk usage, and uptime — updated every 10 seconds.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CH8_CONTROL_URL` | `https://control.ch8ai.com.br` | Control server URL |
| `CH8_PORT` | `7878` | Port this node advertises (used internally) |
| `CH8_POLL_INTERVAL` | `30` | Seconds between peer discovery polls |
| `CH8_HEARTBEAT` | `15` | Seconds between heartbeats |

---

## Files

```
connect/
├── __init__.py       # Module
├── __main__.py       # python -m connect → starts daemon
├── auth.py           # Login flow + token auth + credential storage
├── coordinator.py    # HTTP client for control server
├── daemon.py         # Background daemon (registration, heartbeat, peer discovery)
├── README.md
└── server/
    ├── app.py        # FastAPI control server + web dashboard
    ├── models.py     # Pydantic request/response models
    ├── store.py      # In-memory node + auth registry
    ├── Dockerfile
    └── docker-compose.yml
```
