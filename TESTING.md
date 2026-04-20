# Testing CH8 Agent

## Quick Start

### Prerequisites
- Python 3.12+
- Redis running with password "1q2w3e4r"
- Virtual environment activated

### Start the Cluster

```bash
cd /data/ch8-agent
bash test-cluster.sh
```

This will:
1. Start master on port 50051
2. Start worker-001 on port 50052
3. Start worker-002 on port 50053
4. Verify workers registered with master

### Run Tests

```bash
# Check cluster status
python test-e2e.py

# Submit test tasks
python test-submit.py
```

### Monitor

```bash
# Watch master logs
tail -f /tmp/ch8-master.log

# Watch worker logs
tail -f /tmp/ch8-worker1.log
tail -f /tmp/ch8-worker2.log

# Check Redis
redis-cli -a 1q2w3e4r SMEMBERS cluster:workers
redis-cli -a 1q2w3e4r KEYS "cluster:worker:*"
```

### Stop the Cluster

```bash
pkill -f "python.*cluster/(master|worker)"
```

Or use the PIDs shown by test-cluster.sh.

## Architecture

```
┌─────────────────┐
│  Master (50051) │
│  - Redis disco  │
│  - gRPC server  │
│  - Task queue   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼────┐ ┌─▼──────┐
│Worker 1│ │Worker 2│
│ 50052  │ │ 50053  │
└────────┘ └────────┘
    │         │
    └────┬────┘
         │
    ┌────▼─────┐
    │  Redis   │
    │ Discovery│
    └──────────┘
```

## Components

### Master (`cluster/master.py`)
- Coordinates cluster
- Maintains worker registry via Redis
- Assigns tasks to workers
- Aggregates results

### Worker (`cluster/worker.py`)
- Registers with master on startup
- Sends heartbeats every 10s
- Executes tasks received via gRPC
- Reports results back to master

### Discovery (`cluster/discovery.py`)
- Redis-based service discovery
- Workers register with metadata
- TTL-based expiration (2x heartbeat)
- Capability-based search

### Protocol (`cluster/proto/cluster.proto`)
- gRPC service definitions
- `MasterService`: Registration, heartbeat, results
- `WorkerService`: Task assignment, status, cancellation

## Current Status

### Sprint 1 ✅ Complete
- [x] Redis discovery
- [x] Master gRPC server
- [x] Worker gRPC client
- [x] Task assignment end-to-end
- [x] Demo: 1 master + 2 workers

### Sprint 2 🚧 Next
- [ ] Master task queue → worker flow
- [ ] HTTP API for task submission
- [ ] Real model execution in workers
- [ ] Task retry logic
- [ ] Better worker selection

## Logs

All logs are structured JSON via structlog:

```json
{
  "timestamp": "2026-04-20T17:55:02Z",
  "level": "info",
  "event": "worker_registered",
  "worker_id": "worker-001",
  "capabilities": ["general_agent", "python_execution"]
}
```

Useful queries:

```bash
# Show all worker registrations
grep worker_registered /tmp/ch8-master.log

# Show task executions
grep executing_task /tmp/ch8-worker*.log

# Show heartbeats
grep heartbeat_received /tmp/ch8-master.log
```

## Troubleshooting

### Workers not registering
- Check Redis is running: `redis-cli -a 1q2w3e4r ping`
- Check Redis URL in config/master.yaml
- Check master logs: `cat /tmp/ch8-master.log`

### Tasks not executing
- Check worker logs for errors
- Verify gRPC ports not blocked
- Check worker is registered: `python test-e2e.py`

### Connection refused errors
- Make sure master started before workers
- Check ports not already in use: `netstat -tlnp | grep 5005`

## Performance

Current benchmarks (local testing):
- Worker registration: <100ms
- Heartbeat latency: <10ms
- Task assignment: <50ms
- Redis lookup: <5ms

Target (production):
- Support 100+ workers per master
- <100ms task assignment latency
- 99.9% heartbeat success rate
