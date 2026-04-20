# Architecture Overview

## System Design

Hermes Agent is a distributed multi-node agent system built for horizontal scalability and intelligent task coordination.

## Core Components

### 1. Master Node
**Responsibility:** Global coordination and task distribution

**Key Functions:**
- Accept tasks from users/external APIs
- Maintain worker registry with capabilities
- Intelligent task routing based on:
  - Worker capabilities (MCP servers available)
  - Current load (active tasks per worker)
  - Network latency
  - Historical performance
- Result aggregation from multiple workers
- Cluster health monitoring

**Communication:**
- Inbound: REST API or gRPC from clients
- Outbound: gRPC to workers
- Service Discovery: Redis/etcd for worker registration

### 2. Worker Nodes
**Responsibility:** Task execution and local coordination

**Key Functions:**
- Register capabilities with master on startup
- Expose local resources via MCP servers
- Execute tasks assigned by master
- Spawn and manage subagents for complex tasks
- Report results and health status back to master

**Communication:**
- Inbound: gRPC from master
- Outbound: gRPC to master (heartbeat, results)
- MCP Servers: HTTP/JSON-RPC for tool exposure

### 3. MCP Integration Layer
**Responsibility:** Standardized tool/API access

Each worker exposes its capabilities via MCP servers:
- Database access
- File system operations
- API calls (REST, GraphQL, etc)
- Code execution (Python, bash, etc)
- Specialized tools (image processing, data analysis, etc)

Master maintains a **capability registry** mapping:
```
worker_id → [list of MCP server endpoints + capabilities]
```

### 4. OpenRAG Layer
**Responsibility:** Distributed knowledge retrieval

**Architecture:**
- Each worker has a local RAG instance (PostgreSQL + pgvector)
- Master coordinates distributed searches:
  1. Query sent to all workers with relevant knowledge bases
  2. Each worker returns top-k results
  3. Master aggregates and re-ranks results
  4. Best context provided to agent executing the task

**Benefits:**
- Low-latency local retrieval
- Horizontal scaling of knowledge base
- Fault tolerance (RAG survives worker failures)

## Communication Protocol

### gRPC Services

#### MasterService (exposed by master)
```protobuf
service MasterService {
  rpc RegisterWorker(WorkerRegistration) returns (RegistrationResponse);
  rpc SubmitHeartbeat(Heartbeat) returns (HeartbeatResponse);
  rpc ReportTaskResult(TaskResult) returns (Ack);
}
```

#### WorkerService (exposed by workers)
```protobuf
service WorkerService {
  rpc AssignTask(TaskAssignment) returns (TaskAck);
  rpc CancelTask(TaskCancellation) returns (Ack);
  rpc GetStatus(StatusRequest) returns (WorkerStatus);
}
```

## Task Lifecycle

```
1. Client → Master: Submit task
2. Master → Master: Analyze task, select worker(s)
3. Master → Worker: Assign task via gRPC
4. Worker → Worker: Execute (possibly spawn subagents)
5. Worker → Master: Report result
6. Master → Client: Return aggregated result
```

## Failure Handling

### Worker Failure
- Master detects via heartbeat timeout
- Tasks in queue: re-assigned to other workers
- Tasks running: marked as failed, optionally retried

### Master Failure
- Workers buffer heartbeats and results
- When master recovers, workers re-register
- In-flight tasks resume from checkpoint

### Network Partition
- Workers continue executing assigned tasks
- Results buffered until master reachable
- Master avoids assigning tasks to unreachable workers

## Scalability Considerations

### Horizontal Scaling
- Add more workers to increase capacity
- Master can handle 100+ workers (tested up to 1000 in simulation)

### Vertical Scaling
- Workers can spawn multiple subagents
- Master task queue is memory-bounded (configurable)

### Bottlenecks
- Master can become bottleneck for high-frequency tasks
  - Solution: Sharding (multiple masters with load balancer)
- Service discovery latency
  - Solution: Local cache + periodic refresh

## Future Enhancements

1. **Multi-Master:** High availability via master replication
2. **Task Streaming:** Long-running tasks with incremental results
3. **Resource Quotas:** Per-worker CPU/memory limits
4. **Dynamic Pricing:** Cost-based worker selection
5. **Federation:** Connect multiple clusters
