# CH8 Connect

Tailscale-style auto-mesh for CH8 Agent nodes.

Install on any machine, authenticate once, and the node automatically discovers and joins your cluster — no manual IP configuration, no Redis setup, no VPN required.

---

## Quick Start

### Option 1 — Interactive login (recommended for first machine)

```bash
ch8 login       # opens browser for authentication
ch8 up          # daemon starts, node joins your network
ch8 nodes       # see all connected nodes
```

### Option 2 — Pre-auth token (headless, CI, embedded devices)

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
│  PUT  /nodes/:id/heartbeat← keepalive                      │
│  GET  /nodes              ← peer discovery                 │
└───────────────┬──────────────────────────┬─────────────────┘
                │ register + heartbeat      │ register + heartbeat
                ▼                           ▼
        ┌───────────────┐           ┌───────────────┐
        │  Node A       │           │  Node B       │
        │  (your laptop)│◄─────────►│  (Raspberry Pi│
        │               │  gRPC     │               │
        └───────────────┘           └───────────────┘
```

1. `ch8 up` starts the **connect daemon** (`ch8d`) in the background
2. Daemon authenticates with the control server using saved credentials or a token
3. Registers this node: hostname, IP, port, capabilities, OS
4. Polls the control server every 30s for peer list
5. When new peers appear, they're immediately available for task dispatch
6. Heartbeat every 15s keeps the node listed as online
7. On `ch8 down`, node is gracefully deregistered

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

## Running the Control Server

```bash
cd connect/server
docker compose up -d
```

Or directly:
```bash
pip install fastapi uvicorn pydantic httpx
uvicorn connect.server.app:app --host 0.0.0.0 --port 8000
```

Environment variables:
| Variable | Default | Description |
|----------|---------|-------------|
| `CH8_CONTROL_URL` | `https://control.ch8ai.com.br` | Control server URL |
| `CH8_CONTROL_BASE_URL` | same | Public URL for verification links |
| `CH8_PORT` | `7878` | Port this node advertises |
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
    ├── app.py        # FastAPI control server
    ├── models.py     # Pydantic request/response models
    ├── store.py      # In-memory node + auth registry
    ├── Dockerfile
    └── docker-compose.yml
```
