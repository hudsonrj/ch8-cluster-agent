# CH8 Agent — Complete AI Operations Platform

## Overview

CH8 Agent is a distributed AI operations platform that turns any machine — from Raspberry Pi to cloud VPS — into a node of an intelligent, self-healing cluster. It replaces 10+ traditional tools (Zabbix, Grafana, Jira, PagerDuty, Elastic, Terraform, Ansible, etc.) with a single platform powered by AI agents.

**One command to install. One conversation to operate.**

---

## Core Capabilities

### 1. Security Operations Center (SOC)

CH8 implements enterprise-grade security with 7 active protection layers:

| Layer | Protection | Details |
|-------|-----------|---------|
| 1 | Authentication | Bearer token on ALL endpoints. Node-to-node encrypted auth |
| 2 | Sanitization | Blocks rm -rf, fork bombs, docker injection, path traversal |
| 3 | Credentials | Zero hardcoded. All in env files (chmod 600). Never in code |
| 4 | Rate Limiting | Redis sliding window. 60/min execute, 30/min chat |
| 5 | Headers + Relay | nginx security headers. Relay auth for proxied endpoints |
| 6 | SQL Injection | 25+ patterns: UNION SELECT, DROP, COPY TO, pg_sleep, etc |
| 7 | Prompt Injection | 20+ patterns: jailbreak, role manipulation, system extraction |

**Active Scanners:**
- Port security scanning (every 10 minutes)
- File integrity monitoring (SHA-256 on critical files)
- TCP connection anomaly detection
- User session monitoring (failed logins, unusual hours)
- Automated ITSM ticket creation for security findings

**Audit Trail:** 11,500+ events recorded. Full compliance logging.

**Pentest Results:** 12/12 vectors tested and PASSED.

---

### 2. ITSM / Helpdesk (Autonomous)

Fully automated incident management with zero human intervention for L1/L2:

```
DETECT -> OPEN TICKET -> INVESTIGATE -> FIX -> VALIDATE -> CLOSE
```

**Ticket Categories:**
- `service_down` — Service outage (auto-restart)
- `performance` — Degradation / slow response
- `disk_full` — Storage critical (auto-cleanup)
- `config` — Configuration drift detected
- `security` — Threat or vulnerability found

**SLA Enforcement:**
- Critical: 1 hour (auto-escalate)
- High: 4 hours
- Medium: 24 hours
- Low: 72 hours

**Real Example:**
```
03:17 Oracle container crashed
03:17 Ticket #47 opened (severity: critical)
03:18 Investigating... ORA-00600 internal error
03:18 Fix: docker restart oracle-free
03:19 Validation: Oracle OK, port 1521 responding
03:19 Ticket resolved. MTTR: 2 minutes.
```

---

### 3. Self-Healing Infrastructure

The cluster monitors itself and fixes problems autonomously:

| Event | Auto-Response |
|-------|--------------|
| Service crashes | Detect -> ticket -> restart -> validate -> close |
| Disk at 95% | Alert -> identify large files -> cleanup suggestion |
| DB replica lag | Detect -> reconnect subscription -> refresh |
| Node unreachable | Recovery agent -> SSH -> restart daemon |
| Rate limit spike | Log -> identify source -> block if malicious |
| Agent disappears | Daemon sanitizes state -> auto-restart |

**High Availability:**
- Master/standby election via priority ranking
- Central agents check `is_master()` before acting
- Automatic failover if master goes down
- Zero-downtime rolling updates via `scripts/restart.sh`

---

### 4. Build Applications via Conversation

Tell the cluster what you need — it codes, tests, and deploys:

```
You: "Create a monitoring agent for DNS resolution times"
AI: Creating project... writing dns_optimizer.py... testing... PASSED!
    -> Deployed as agent on manager1
```

**Innovation Lab:**
- 50 project limit (auto-manages)
- Autonomous ideation + code generation
- Auto-test in sandbox (isolated)
- Auto-fix with AI (up to 3 attempts)
- Score ranking (0-100) by relevance
- Kanban pipeline: Fixing -> Testing -> Completed -> Deployed
- Top-scoring projects auto-deployed as cluster agents

**HubBuildAI:**
- Full application builder from prompts
- Generates complete web apps (frontend + backend + database)

---

### 5. Observability & Log Analytics

Grafana-style log analytics powered by AI — without the complexity:

- **250,000+ logs** ingested from all sources
- **Sources:** syslog, Docker containers, nginx, Oracle alert_log, PostgreSQL
- **AI Classification:** critico, seguranca, acao, info, transitorio, atencao
- **Time-series** visualization with trends
- **Failure predictions:** "CPU will exhaust in 4h at current rate"
- **Auto-ticket:** Recurring patterns (3+ in 10min) -> ITSM ticket

---

### 6. Database Operations

**PostgreSQL:**
- Master + Replica monitoring (logical streaming)
- Replication lag detection + auto-reconnect
- Connection metrics, query performance

**Oracle:**
- Container health monitoring
- Tablespace usage, alert log
- Auto-restart on crash

---

### 7. Natural Language Interface

Talk to your entire infrastructure from anywhere:

**Examples:**
```
"Restart the nginx service on vmi"
"Show disk usage across all nodes"
"What happened at 3am?"
"Deploy latest code to all nodes"
"Create a backup of database X"
"Run a security scan on all nodes"
"How much is this cluster costing?"
```

---

### 8. Dashboard (12 Specialized Pages)

| Page | Description |
|------|-------------|
| Nodes | Real-time CPU/RAM/disk per node, agents, chat |
| Cluster | Aggregated view, topology graph, model catalog |
| Observability | Security findings, errors, predictions |
| Strategic Room | Agent graph, activity feed, command bar |
| Ops Deck | Health score, SLA%, cost/hr, nginx sites |
| Databases | All instances, replication, query metrics |
| Architecture | C4-style topology, service inventory |
| Logs | Classification donut, time series, predictions |
| Lab | Innovation Kanban, scores, documentation |
| Analytics | FinOps: cost/model, cost/agent, projections |
| ITSM | Ticket Kanban, SLA tracker |
| Security | 7 layers, threat map, audit feed |

---

### 9. Workflow Studio

Visual drag-and-drop editor for AI workflows:
- Connect nodes, agents, models as draggable blocks
- AI Copilot suggests workflow designs
- Execution distributed across cluster
- React Flow canvas with real-time state

---

### 10. FinOps & Analytics

- Cost per agent, per model, per node
- Burn rate: $/hr, $/day, $/month, $/year
- Resource distribution charts
- Model catalog (Cloud + local Ollama)
- Projections: semester, annual

---

## Agents (15+)

### Always Running (All Nodes)
- Orchestrator — AI command center with tool calls
- Server Monitor — Metrics, predictions, threats
- Mesh Relay — P2P communication bridge
- Log Shipper — All logs -> PostgreSQL

### Central (HA Master Only)
- Log Analyzer — Pattern detection -> tickets
- Ticket Resolver — Full ITSM lifecycle
- DB Failover — PostgreSQL monitoring
- Security Scanner — Port, integrity, connections

### Optional (Context-Dependent)
- Telegram Bot, Oracle Monitor, Innovation Lab, Recovery Agent
- Knowledge Agent, TTS/STT, RAG Agent, PG Performance Tuner

---

## Comparisons

| Feature | CH8 Agent | Traditional Stack |
|---------|-----------|-------------------|
| Monitoring | Built-in | Zabbix + Grafana |
| Logs | Built-in (AI) | ELK / Loki |
| ITSM | Autonomous | Jira + PagerDuty |
| Security | 7 layers | CrowdStrike + SIEM |
| Deployment | Chat | Terraform + Ansible |
| App Building | Conversation | Months of dev |
| Cost | $0 (your hardware) | $500+/month |
| Setup | 60 seconds | Days/weeks |

---

## License

MIT — Use it, modify it, deploy it. No restrictions.
