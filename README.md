# CH8 Distributed Agent 🌐⚡

**Distributed Multi-Node Agent System with Intelligent Coordination**

A revolutionary distributed agent architecture built on top of proven AI agent technology, enabling true multi-node coordination, intelligent task delegation, and distributed RAG.

## 🎯 Vision

Transform single-machine agent systems into a horizontally scalable cluster where:

- **Master node** coordinates global strategy and delegates tasks
- **Worker nodes** execute tasks independently with their own subagents
- **MCP (Model Context Protocol)** enables seamless tool/API integration
- **OpenRAG** provides distributed knowledge retrieval
- **Intelligent routing** matches tasks to the best-suited nodes

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MASTER NODE                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Master Agent                                   │   │
│  │  - Global coordination                          │   │
│  │  - Task distribution                            │   │
│  │  - Result aggregation                           │   │
│  └──────────┬──────────────────────────────────────┘   │
│             │ gRPC/WebSockets                           │
│  ┌──────────┴──────────┐  ┌────────────────────┐      │
│  │ SubAgent 1          │  │ SubAgent N         │      │
│  └─────────────────────┘  └────────────────────┘      │
└─────────────────────────────────────────────────────────┘
              │                              │
      ┌───────┴───────┐              ┌──────┴───────┐
      │  WORKER 1     │              │  WORKER N    │
      │ ┌───────────┐ │              │ ┌──────────┐ │
      │ │Agent      │ │              │ │Agent     │ │
      │ │Principal  │ │              │ │Principal │ │
      │ └─────┬─────┘ │              │ └────┬─────┘ │
      │   ┌───┴───┐   │              │  ┌───┴────┐ │
      │   │SubAg 1│   │              │  │SubAg N │ │
      │   └───────┘   │              │  └────────┘ │
      └───────────────┘              └──────────────┘
```

## ✨ Key Features

### 🔄 Distributed Coordination
- Master-worker topology with intelligent load balancing
- Health monitoring and automatic failover
- Task queue with priority scheduling

### 🔌 MCP Integration
- Every node exposes its capabilities via MCP servers
- Master maintains capability registry
- Intelligent routing based on available tools/APIs

### 🧠 OpenRAG Distribution
- Each node has local RAG for low-latency retrieval
- Distributed search coordinated by master
- Smart context aggregation across nodes

### 📡 Communication
- gRPC for high-performance inter-node messaging
- Redis/etcd for service discovery
- WebSocket fallback for simplified debugging

### 🛡️ Resilience
- Automatic node failure detection
- Task re-routing on node failure
- State persistence for crash recovery

## 🚀 Quick Start

**Prerequisites:**
- Python 3.12+
- Redis (with password: 1q2w3e4r)
- 4GB+ RAM recommended

```bash
# Clone and setup
git clone https://github.com/hudsonrj/ch8-distributed-agent.git
cd ch8-distributed-agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start the cluster
bash test-cluster.sh

# In another terminal: Run tests
python test-e2e.py
python test-submit.py

# Stop cluster
bash stop-cluster.sh
```

For detailed testing instructions, see [TESTING.md](TESTING.md).

## 📚 Documentation

- [Architecture Overview](docs/architecture.md)
- [Getting Started](docs/getting-started.md)
- [Configuration Guide](docs/configuration.md)
- [MCP Integration](docs/mcp-integration.md)
- [OpenRAG Setup](docs/openrag-setup.md)
- [Deployment Guide](docs/deployment.md)

## 🛠️ Technology Stack

- **Python 3.11+**
- **gRPC** - Inter-node communication
- **Redis/etcd** - Service discovery
- **PostgreSQL + pgvector** - OpenRAG storage
- **MCP** - Model Context Protocol
- **Docker** - Containerization
- **Kubernetes** (optional) - Orchestration

## 📦 Project Structure

```
ch8-distributed-agent/
├── cluster/              # Core cluster logic
│   ├── master.py        # Master node implementation
│   ├── worker.py        # Worker node implementation
│   ├── protocol.py      # Communication protocol
│   ├── discovery.py     # Service discovery
│   └── delegation.py    # Task delegation logic
├── mcp_integration/     # MCP capability registry
├── openrag_integration/ # Distributed RAG
├── config/              # Configuration files
├── docs/                # Documentation
├── tests/               # Tests
└── examples/            # Usage examples
```

## 🎯 Roadmap

### Phase 1: Foundation (Week 1) ✅ COMPLETE
- [x] Project setup
- [x] Basic master-worker communication (gRPC)
- [x] Service discovery (Redis)
- [x] Simple task delegation
- [x] **Demo:** 1 master + 2 workers running locally

**Sprint 1 delivered (2026-04-20):**
- Redis-based worker registration with TTL
- Master gRPC server (registration, heartbeat, results)
- Worker gRPC client (connects, registers, executes tasks)
- End-to-end task flow working
- Structured logging throughout
- Testing scripts and documentation

See [TESTING.md](TESTING.md) for how to run the demo!

### Phase 2: Network Distribution (Week 2)
- [ ] gRPC implementation
- [ ] Health checks & failover
- [ ] Multi-machine testing

### Phase 3: MCP & RAG (Week 3-4)
- [ ] MCP capability registry
- [ ] OpenRAG per-node setup
- [ ] Distributed search coordination

### Phase 4: Production Ready (Week 5+)
- [ ] Monitoring (Prometheus + Grafana)
- [ ] Centralized logging
- [ ] Kubernetes deployment
- [ ] Performance tuning

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🔗 Links

- **Base Technology:** [Hermes Agent](https://hermes-agent.nousresearch.com/)
- **OpenRAG:** [langflow-ai/openrag](https://github.com/langflow-ai/openrag/)
- **MCP Spec:** [Model Context Protocol](https://modelcontextprotocol.io/)

## 👥 Authors

- **Hudson RJ** ([@hudsonrj28](https://github.com/hudsonrj28))
- Built with assistance from OpenClaw AI

---

**Status:** ✅ Sprint 1 Complete | **Version:** 0.2.0-alpha | **Progress:** 50%

**Last updated:** 2026-04-20 | See [docs/decisions.md](docs/decisions.md) for technical decisions
