# CH8 Agent

**Complete AI Operations Platform — SOC, ITSM, DevOps, Innovation Lab — All Autonomous.**

CH8 Agent turns any machine into a node of a self-healing, self-monitoring, self-evolving AI cluster. From Security Operations Center to Helpdesk, from auto-remediation to building new applications — just talk to it.

## What It Does

| Capability | Description |
|-----------|-------------|
| **SOC (Security)** | 7-layer protection. Port scanning, file integrity, SQL/prompt injection blocking, rate limiting. Pentest 12/12 PASS. |
| **ITSM (Helpdesk)** | Autonomous ticket management. AI detects → opens ticket → investigates → fixes → validates → closes. Zero human intervention. |
| **Self-Healing** | Detects failures, restarts services, failover databases, SSH recovery. HA election with master/standby. |
| **App Builder** | Describe what you need in natural language. The cluster codes, tests, and deploys. Innovation Lab with 50+ projects. |
| **Observability** | 250k+ logs collected, classified (AI), visualized. Failure predictions. Grafana-style analytics without Grafana. |
| **Database Ops** | PostgreSQL master + replica monitoring. Oracle health. Replication lag detection. Auto-reconnect. |
| **Chat Interface** | Talk to your infrastructure via Dashboard, Telegram, or Slack. "Restart nginx on all nodes" → done. |
| **FinOps** | Cost per agent, per model, per node. Burn rate projections. Resource distribution charts. |

## Quick Install

```bash
# Linux / macOS
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install.sh | bash

# Raspberry Pi
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-rpi.sh | bash

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -c "iwr -useb https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-win32.ps1 | iex"

# Android (Termux)
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/master/scripts/install-android.sh | bash
```

## Setup

```bash
ch8 config ai              # Configure AI provider (Bedrock, OpenAI, Ollama, Groq, Anthropic)
ch8 up --token <TOKEN>     # Join network — node appears on dashboard immediately
ch8 status                 # See nodes, agents, peers
```

## Commands

| Command | Description |
|---------|-------------|
| `ch8 up` | Start all agents, join network |
| `ch8 down` | Stop all agents gracefully |
| `ch8 status` | Show node status, agents, peers |
| `ch8 config ai` | Configure AI provider |
| `ch8 config channels` | Configure Telegram/Slack |
| `ch8 config tools` | Enable/disable tools |
| `ch8 update` | Pull latest code + restart |

## Agents (15+)

### Core (All Nodes)
| Agent | Function |
|-------|----------|
| **Orchestrator** | AI command center. Executes tasks via tool calls (shell, files, Docker, HTTP) |
| **Server Monitor** | CPU/RAM/disk metrics, threat detection, failure prediction |
| **Mesh Relay** | P2P communication bridge between isolated networks |
| **Log Shipper** | Collects logs from all sources → PostgreSQL (60s cycle) |

### Central (HA — Master Only)
| Agent | Function |
|-------|----------|
| **Log Analyzer** | Detects recurring error patterns → creates ITSM tickets |
| **Ticket Resolver** | Full ITSM lifecycle: investigate → fix → validate → close (2min cycle) |
| **DB Failover** | Monitors PostgreSQL master/replica, detects replication issues |
| **Security Scanner** | Port scan, file integrity, TCP analysis, session monitoring (10min cycle) |

### Optional (Auto-detected)
| Agent | Function |
|-------|----------|
| **Telegram Bot** | Bidirectional Telegram interface with typing indicator |
| **Oracle Monitor** | Oracle DB health, tablespace, alert log (where Oracle runs) |
| **Innovation Lab** | Autonomous R&D: generates ideas, codes, tests, deploys projects |
| **Recovery Agent** | SSH auto-heal for unreachable nodes |
| **Knowledge Agent** | Obsidian-style knowledge base with full-text search |
| **TTS/STT** | Text-to-speech and speech-to-text (non-low-RAM nodes) |
| **RAG Agent** | Retrieval-augmented generation over cluster docs |

## Security (7 Layers)

```
Layer 1 — Authentication    Bearer token on ALL endpoints
Layer 2 — Sanitization      Blocks rm -rf, fork bombs, docker injection, path traversal
Layer 3 — Credentials       Zero hardcoded. All in env files (chmod 600)
Layer 4 — Rate Limiting     Redis sliding window (60/min execute, 30/min chat)
Layer 5 — Headers + Relay   nginx security headers, relay auth for proxied endpoints
Layer 6 — SQL Injection     25+ patterns blocked (UNION SELECT, DROP, pg_sleep...)
Layer 7 — Prompt Injection  20+ patterns blocked (jailbreak, role manipulation...)
```

**Pentest Results: 12/12 PASS** (auth bypass, RCE, path traversal, docker injection, SQL injection, prompt injection, fork bomb, rate limit, relay auth, curl|bash, credential exposure, audit integrity)

## ITSM (Autonomous Helpdesk)

```
DETECT (log patterns) → OPEN TICKET → INVESTIGATE → FIX → VALIDATE → CLOSE
```

- **Categories**: service_down, performance, disk_full, config, security
- **SLA**: critical=1h, high=4h, medium=24h, low=72h
- **Auto-escalation** on SLA breach
- **Kanban board** in dashboard

## Dashboard (12 Pages)

| Page | Description |
|------|-------------|
| **Nodes** | Real-time metrics per node, agents, services, chat |
| **Cluster** | Aggregated view, topology graph, model catalog |
| **Observability** | Security findings, errors, predictions, disk alerts |
| **Strategic Room** | Force-directed agent graph, activity feed, command bar |
| **Ops Deck** | GCP-style cockpit: health score, SLA, cost, nginx sites |
| **Databases** | All DB instances, replication monitor, query metrics |
| **Architecture** | C4-style topology, service inventory, data flow |
| **Logs** | Grafana-style: classification donut, time series, predictions |
| **Lab** | Innovation Lab Kanban, project scores, documentation |
| **Analytics** | FinOps: cost/model, cost/agent, resource distribution |
| **ITSM** | Ticket Kanban board, SLA tracker, auto-resolution timeline |
| **Security** | Cyber-themed: 7 layers, threat map, audit feed, posture score |

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  CH8 Control + Auth Portal  (app.ch8ai.com.br)                │
│  Dashboard 12 pages │ Clerk Auth │ API Gateway                │
└────────────────────────────┬──────────────────────────────────┘
                             │ HTTPS + Tailscale Mesh
         ┌───────────────────┼───────────────────┐
         │                   │                   │
┌────────┴────────┐  ┌──────┴──────┐  ┌────────┴───────┐
│  manager1       │  │  vmi (VPS)  │  │  raspberry pi  │
│  15 agents      │  │  DB replica │  │  4 agents      │
│  PG + Oracle    │  │  6 agents   │  │  ARM64         │
│  Redis          │  │  Public IP  │  │  Low-RAM mode  │
└─────────────────┘  └─────────────┘  └────────────────┘
```

Each node runs:
- **Orchestrator** — AI-powered agent (tool calls: shell, docker, files, http)
- **Connect Daemon** — Heartbeats, peer discovery, metrics
- **Server Monitor** — System metrics, predictions, threats
- **Security Middleware** — 7 layers active on every request
- **Log Shipper** — Collects all logs → PostgreSQL
- **Channel Listeners** — Telegram, Slack (bidirectional)

## AI Providers

| Provider | Type | Setup |
|----------|------|-------|
| AWS Bedrock | Cloud | Region + IAM credentials |
| OpenAI | Cloud | API key |
| Anthropic | Cloud | API key |
| Groq | Cloud | API key (fast inference) |
| Ollama | Local | No key needed (free, private) |

## Innovation Lab

The cluster has an autonomous R&D engine:

1. **Submit ideas** via dashboard or chat ("create a DNS monitor")
2. **AI generates** the project code automatically
3. **Tests run** in sandbox (isolated)
4. **Auto-fix** on failure (up to 3 attempts)
5. **Score & rank** projects by relevance
6. **Deploy winners** as new agents on the cluster
7. **Kanban board** tracks: Fixing → Testing → Completed → Deployed

Currently: 20 projects, 10 passed, 5 deployed as agents.

## What You Can Say

```
"How is the PostgreSQL replication?"
"Restart docker containers on vmi"
"Show me all security alerts from today"
"Create a monitoring agent for my Redis"
"What's using 80% CPU on the raspberry pi?"
"Deploy latest code to all nodes"
"Open a ticket for the disk space issue"
"Build a webhook that listens on port 9000"
"Show cluster health report"
"Run a security scan on all nodes"
```

## Self-Healing Examples

| Event | Auto-Response |
|-------|--------------|
| Oracle container crashes | Detect → ticket → docker restart → validate → close (MTTR: 2 min) |
| Disk at 95% | Alert → identify large files → cleanup → validate |
| PostgreSQL replica lag | Detect → reconnect subscription → refresh publication |
| Node unreachable | Recovery agent → SSH → restart ch8 daemon |
| Rate limit spike | Log → identify source → block if malicious |
| Service degradation | Create ticket → investigate → scale/restart → close |

## Tech Stack

- **Language**: Python 3.10+
- **API**: FastAPI + Uvicorn
- **Database**: PostgreSQL 16 (logical replication)
- **Cache**: Redis (rate limiting, queues, pub/sub)
- **Networking**: Tailscale mesh + direct LAN
- **Auth**: Clerk (portal) + Bearer tokens (API)
- **AI**: Claude Sonnet 4.5 (default), supports any provider
- **Frontend**: Vanilla JS + CSS (no framework bloat)
- **Containers**: Docker (optional, for services)

## Requirements

- Python 3.10+
- Tailscale (recommended for multi-network)
- 512MB+ RAM (low-RAM mode skips heavy agents)
- Any OS: Linux, macOS, Windows (WSL), Android (Termux)

## License

MIT — Use it, modify it, deploy it. No restrictions.
