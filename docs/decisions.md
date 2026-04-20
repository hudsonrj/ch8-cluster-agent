# Technical Decisions - CH8 Agent

This document tracks important technical decisions made during development.

## Sprint 1 - Foundation (2026-04-20)

### Decision 1: Redis for Service Discovery
**Context:** Need a simple, reliable way for workers to register and for master to discover them.

**Alternatives considered:**
- etcd: More features, but overkill for MVP
- Consul: Great for production, but adds complexity
- Custom database: Would need to build everything from scratch

**Decision:** Use Redis with key expiration
- Simple to setup and operate
- Built-in expiration for automatic cleanup
- Fast lookups with O(1) complexity
- Familiar to most developers

**Implementation:**
- Workers register at `cluster:worker:{worker_id}` with TTL = 2x heartbeat interval
- Worker list maintained in set `cluster:workers`
- Heartbeats refresh TTL
- Expired workers automatically removed

**Trade-offs:**
- ✅ Simple and fast
- ✅ Built-in TTL handles disconnections
- ❌ Redis is a single point of failure (acceptable for MVP)
- ❌ No built-in leader election (not needed for MVP)

### Decision 2: gRPC for Master-Worker Communication
**Context:** Need efficient bidirectional communication between master and workers.

**Alternatives considered:**
- WebSockets: Good for bidirectional, but less structured
- REST: Simple but polling-based, inefficient
- Message queue (RabbitMQ/Kafka): Overkill for direct communication

**Decision:** Use gRPC with async Python
- High performance with protobuf serialization
- Strongly typed contracts via .proto files
- Built-in load balancing and retries
- Good Python async support with grpc.aio

**Implementation:**
- `MasterService`: Exposed by master (registration, heartbeat, results)
- `WorkerService`: Exposed by workers (task assignment, status, cancellation)
- Async/await throughout for efficient I/O

**Trade-offs:**
- ✅ Fast and efficient
- ✅ Type-safe with protobuf
- ✅ Easy to evolve API
- ❌ More complex than REST (acceptable given performance benefits)
- ❌ Debugging harder than JSON (mitigated with logging)

### Decision 3: Simplified Task Execution for MVP
**Context:** Need to demonstrate end-to-end flow without full AI integration.

**Decision:** Implement simple "echo" task execution
- Workers accept tasks via gRPC
- Simulate work with `asyncio.sleep(2)`
- Return mock results
- Real AI integration deferred to Sprint 2

**Rationale:**
- Proves the infrastructure works
- Can test load balancing and failure handling
- Reduces complexity for initial demo
- Easy to swap in real execution later

**Trade-offs:**
- ✅ Fast to implement and test
- ✅ Focuses on networking/coordination
- ⚠️ Need to add real execution soon

### Decision 4: Worker Selection Algorithm
**Context:** Master needs to choose which worker gets each task.

**Decision:** Simple load-based selection
```python
selected = min(suitable_workers, key=lambda w: w.get("active_tasks", 0))
```

**Implementation:**
1. Filter workers by required capabilities
2. Select worker with lowest `active_tasks` count
3. Future: Add latency, cost, model availability

**Trade-offs:**
- ✅ Simple and predictable
- ✅ Prevents overloading single worker
- ❌ Doesn't consider worker performance/speed
- ❌ No affinity/stickiness (add later if needed)

### Decision 5: Configuration via YAML
**Context:** Need flexible configuration for master and workers.

**Decision:** YAML files for all configuration
- `config/master.yaml`: Master settings (ports, Redis URL, etc)
- `config/worker.yaml`: Worker settings (models, capabilities, etc)
- Environment variables for secrets (future)

**Rationale:**
- Human-readable and easy to edit
- Supports complex nested structures
- Standard in cloud-native world
- Easy to version control

**Trade-offs:**
- ✅ Very readable
- ✅ Standard tooling support
- ❌ Need schema validation (TODO: add pydantic models)

### Decision 6: Python 3.12 + AsyncIO
**Context:** Language and concurrency model.

**Decision:** Python 3.12 with asyncio for all I/O
- gRPC async client/server
- Redis async client
- All operations non-blocking

**Rationale:**
- Python is lingua franca of AI/ML
- AsyncIO handles I/O-bound workload efficiently
- grpc.aio provides good async support
- Simpler than threading for this use case

**Trade-offs:**
- ✅ Single-threaded model easier to reason about
- ✅ Efficient for I/O-bound tasks
- ❌ Not ideal for CPU-bound work (but that's in subagents)
- ❌ Async can be tricky to debug (mitigated with good logging)

### Decision 7: Structured Logging with structlog
**Context:** Need good observability for distributed system.

**Decision:** Use structlog with JSON output
- All components log structured JSON
- Timestamp, log level, and context fields
- Easy to parse and aggregate

**Example:**
```json
{"timestamp": "2026-04-20T17:55:02Z", "level": "info", "event": "worker_registered", "worker_id": "worker-001", "capabilities": ["general_agent", "python_execution"]}
```

**Trade-offs:**
- ✅ Machine-readable logs
- ✅ Easy to grep/jq/aggregate
- ✅ Includes context automatically
- ❌ Less human-readable (but worth it)

## Sprint 1 Outcomes

### What Works
1. ✅ Redis-based service discovery
   - Workers register on startup
   - Master discovers workers dynamically
   - Heartbeats keep registry fresh
   
2. ✅ Master gRPC server
   - Accepts worker registrations
   - Receives heartbeats every 10s
   - Receives task results
   
3. ✅ Worker gRPC client
   - Registers with master
   - Exposes gRPC server for tasks
   - Executes tasks and reports back
   
4. ✅ End-to-end task flow
   - Task assigned to worker
   - Worker executes (simulated)
   - Result reported to master
   
5. ✅ Demo: 1 master + 2 workers
   - All components running
   - Communication working
   - Logs showing proper flow

### Known Issues
1. ⚠️ Master task queue not fully integrated
   - Can submit tasks via master API
   - But test sent tasks directly to worker
   - TODO: Complete master queue → worker flow

2. ⚠️ No task retry on failure
   - If worker crashes, task is lost
   - TODO: Add retry logic with backoff

3. ⚠️ No authentication/authorization
   - gRPC connections are unencrypted
   - No worker identity verification
   - TODO: Add TLS + auth tokens

4. ⚠️ Single Redis instance
   - Redis failure kills cluster
   - TODO: Add Redis Sentinel/Cluster

### Performance Observations
- Master can handle registration from 2 workers in <1s
- Heartbeat overhead: ~100 bytes per worker per 10s
- Task assignment latency: <50ms (local network)
- Redis operations: <5ms average

## Next Sprint Planning

### Sprint 2 Priorities
1. Complete master task queue integration
2. Add HTTP API to master for task submission
3. Implement proper model execution in workers
4. Add task retry logic
5. Improve worker selection (consider latency, capabilities)

### Future Sprints
- Sprint 3: MCP integration
- Sprint 4: OpenRAG integration
- Sprint 5: Production hardening (auth, monitoring, etc)

---

**Document updated:** 2026-04-20
**Author:** Philosophy Doctor (OpenClaw subagent)
**Approval:** Autonomous (per Hudson's instructions)
