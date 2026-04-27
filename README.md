# CH8 Agent

**Distributed AI Node Agent — Connect any machine to your AI network.**

CH8 Agent turns any machine into a managed AI node with monitoring, orchestration, and multi-channel communication (Telegram, Slack, Dashboard).

## Quick Install

### Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash
```

### Raspberry Pi
```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-rpi.sh | bash
```

### Windows
```powershell
powershell -ExecutionPolicy Bypass -c "iwr -useb https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install-win32.ps1 | iex"
```
> For best experience on Windows, use WSL2: `wsl --install` then run the Linux installer.

### Manual Install
```bash
git clone https://github.com/hudsonrj/ch8-cluster-agent.git ~/ch8-agent
cd ~/ch8-agent
pip install httpx psutil fastapi uvicorn pydantic
chmod +x ch8
export PATH="$PATH:$(pwd)"
```

## Setup

```bash
# Configure AI provider (Bedrock, OpenAI, Ollama, Anthropic, Groq)
ch8 config ai

# Join a network with a pre-auth token
ch8 up --token <TOKEN>

# Check status
ch8 status
```

## Commands

| Command | Description |
|---------|-------------|
| `ch8 up` | Start agent, join network |
| `ch8 down` | Stop all agents |
| `ch8 status` | Show node status and peers |
| `ch8 config ai` | Configure AI provider |
| `ch8 config channels` | Configure Telegram/Slack |
| `ch8 config tools` | Enable/disable agent tools |
| `ch8 config show` | Show current config |
| `ch8 update` | Pull latest code |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CH8 Control Server (control.ch8ai.com.br)                  │
│  - Dashboard with real-time node monitoring                 │
│  - Chat proxy to any node                                   │
│  - Service agent wizard                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS + Tailscale
         ┌─────────────────┼─────────────────┐
         │                 │                 │
┌────────┴────────┐ ┌─────┴──────┐ ┌───────┴───────┐
│  Node: manager1 │ │ Node: rpi  │ │ Node: laptop  │
│                 │ │            │ │               │
│ - Orchestrator  │ │ - Orch.    │ │ - Orch.       │
│ - Server Mon.   │ │ - Monitor  │ │ - Monitor     │
│ - PostgreSQL    │ │            │ │ - Telegram    │
│   MCP Agent     │ │            │ │               │
│ - Telegram Bot  │ │            │ │               │
└─────────────────┘ └────────────┘ └───────────────┘
```

Each node runs:
- **Orchestrator** — AI-powered agent that executes tasks via tool calls
- **Server Monitor** — Watches CPU/RAM/disk, detects threats, predicts issues
- **Connect Daemon** — Heartbeats, peer discovery, metrics reporting
- **Channel Listeners** — Telegram, Slack (optional, bidirectional)
- **Service Agents** — MCP interfaces to databases, APIs, containers

## AI Providers

| Provider | Config |
|----------|--------|
| AWS Bedrock | Region + IAM credentials |
| OpenAI | API key |
| Anthropic | API key |
| Groq | API key |
| Ollama | Local, no key needed |

## Channels

| Channel | Type | Setup |
|---------|------|-------|
| Dashboard | Interactive | Always available |
| Telegram | Interactive | Bot token + chat_id |
| Slack | Interactive | Bot token + channel_id |
| Discord | Alerts only | Webhook URL |
| Webhook | Alerts only | Any HTTP endpoint |

## Agent Tools

The orchestrator can execute these tools on the node:

- `shell_exec` — Run shell commands
- `docker_exec` — Execute inside containers
- `file_read` / `file_write` — File operations
- `http_request` — HTTP calls
- `service_restart` — Restart Docker/systemd services
- `security_scan` — Security audit
- `node_info` — Cluster node information

## Service Agents (MCP)

Create dedicated agents for services running on the node:

```bash
# Via dashboard: Services modal → "+ Agent" button
# Or via chat: "create an agent for my PostgreSQL database"
```

Service agents expose MCP-style tools (health_check, query, metrics) and register in the dashboard.

## Project Structure

```
ch8-agent/
├── ch8                     # CLI entrypoint
├── agents/
│   ├── orchestrator.py     # Main AI agent (FastAPI + streaming)
│   ├── server_monitor.py   # System monitoring + threat detection
│   ├── telegram_listener.py # Telegram bot integration
│   └── PostgreSQL-agent.py # Example service agent
├── connect/
│   ├── daemon.py           # Background daemon (heartbeats, peers)
│   ├── auth.py             # Authentication (pre-auth tokens)
│   ├── coordinator.py      # Control server client
│   ├── ai_config.py        # AI provider configuration
│   ├── channels.py         # Channel management
│   └── tools_config.py     # Tool definitions + execution
└── scripts/
    └── install.sh          # One-line installer
```

## Requirements

- Python 3.10+
- Tailscale (for mesh networking)
- `pip install httpx psutil fastapi uvicorn pydantic`

## License

MIT
