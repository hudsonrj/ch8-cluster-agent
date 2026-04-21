# CH8 Agent V2 - Implementation Plan

**Data:** 2026-04-21
**Objetivo:** Roadmap técnico para arquitetura federada

---

## 📋 Visão Geral da Migração

### Filosofia: Evolução, não Revolução

**Estratégia:**
- ✅ Manter V1 funcionando
- ✅ Adicionar V2 como camada opcional
- ✅ Migração gradual e reversível
- ✅ Backward compatibility total

---

## 🏗️ Fase 1: Foundation (Sprint 2)

### 1.1 Peer-to-Peer Discovery

**Objetivo:** Nodes descobrem uns aos outros sem servidor central

**Implementação:**

```python
# cluster/p2p/discovery.py

import asyncio
from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf
import json

class P2PDiscovery:
    """
    Multi-protocol peer discovery:
    - mDNS/Zeroconf para LAN
    - Redis Pub/Sub para opcional coordination
    - Manual registration para multi-datacenter
    """

    def __init__(self, node_id, capabilities):
        self.node_id = node_id
        self.capabilities = capabilities
        self.peers = {}  # {node_id: {address, capabilities, last_seen}}

        # Discovery methods
        self.mdns = Zeroconf()
        self.redis_pubsub = None  # Optional

    async def announce(self):
        """Announce this node to network"""

        # 1. mDNS announcement (LAN)
        service_info = ServiceInfo(
            "_ch8agent._tcp.local.",
            f"{self.node_id}._ch8agent._tcp.local.",
            addresses=[self.get_local_ip()],
            port=50100,
            properties={
                'node_id': self.node_id,
                'capabilities': json.dumps(self.capabilities),
                'version': '2.0'
            }
        )
        self.mdns.register_service(service_info)

        # 2. Redis pub/sub (optional, cross-datacenter)
        if self.redis_pubsub:
            await self.redis_pubsub.publish('ch8:discovery', {
                'type': 'announce',
                'node_id': self.node_id,
                'capabilities': self.capabilities,
                'address': f"{self.get_local_ip()}:50100"
            })

    async def discover_peers(self):
        """Discover other nodes"""

        # 1. mDNS browser (LAN)
        browser = ServiceBrowser(
            self.mdns,
            "_ch8agent._tcp.local.",
            handlers=[self._on_service_found]
        )

        # 2. Redis subscription (optional)
        if self.redis_pubsub:
            await self.redis_pubsub.subscribe('ch8:discovery')

    def _on_service_found(self, zeroconf, service_type, name):
        """Handle discovered peer"""
        info = zeroconf.get_service_info(service_type, name)

        peer_id = info.properties.get(b'node_id').decode()
        capabilities = json.loads(
            info.properties.get(b'capabilities').decode()
        )

        self.peers[peer_id] = {
            'address': f"{info.addresses[0]}:{info.port}",
            'capabilities': capabilities,
            'last_seen': time.time()
        }

        logger.info(f"Discovered peer: {peer_id}")
```

**Testes:**
```python
# tests/test_p2p_discovery.py

async def test_local_discovery():
    """Test mDNS discovery on same LAN"""

    # Start node 1
    node1 = P2PDiscovery("node-1", ["python", "text"])
    await node1.announce()

    # Start node 2
    node2 = P2PDiscovery("node-2", ["gpu", "image"])
    await node2.announce()
    await node2.discover_peers()

    # Wait for discovery
    await asyncio.sleep(2)

    # Assert node2 discovered node1
    assert "node-1" in node2.peers
    assert "python" in node2.peers["node-1"]["capabilities"]
```

---

### 1.2 Peer-to-Peer Messaging

**Objetivo:** Communication direta entre nodes

**Implementação:**

```python
# cluster/p2p/messaging.py

class P2PMessenger:
    """
    Direct peer-to-peer messaging via gRPC
    """

    def __init__(self, node_id, address):
        self.node_id = node_id
        self.address = address
        self.connections = {}  # {peer_id: grpc_channel}

    async def send_message(self, peer_id, message):
        """Send message to specific peer"""

        # Get or create connection
        if peer_id not in self.connections:
            peer_address = await self.discovery.get_peer_address(peer_id)
            channel = grpc.aio.insecure_channel(peer_address)
            self.connections[peer_id] = channel

        # Send via gRPC
        stub = P2PServiceStub(self.connections[peer_id])
        response = await stub.SendMessage(
            P2PMessage(
                from_node=self.node_id,
                to_node=peer_id,
                type=message['type'],
                payload=json.dumps(message['payload'])
            )
        )

        return response

    async def broadcast(self, message):
        """Broadcast message to all known peers"""

        tasks = [
            self.send_message(peer_id, message)
            for peer_id in self.discovery.peers
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def query(self, query_type, criteria):
        """Query peers and wait for responses"""

        message = {
            'type': 'query',
            'payload': {
                'query_type': query_type,
                'criteria': criteria
            }
        }

        responses = await self.broadcast(message)

        # Filter successful responses
        valid_responses = [
            r for r in responses
            if not isinstance(r, Exception)
        ]

        return valid_responses
```

**Protocolo gRPC:**

```protobuf
// cluster/proto/p2p.proto

syntax = "proto3";

service P2PService {
  // Send message to peer
  rpc SendMessage(P2PMessage) returns (P2PAck);

  // Request help with task
  rpc RequestCollaboration(CollaborationRequest) returns (CollaborationResponse);

  // Share task result
  rpc ShareResult(TaskResult) returns (Ack);

  // Query capabilities
  rpc QueryCapabilities(CapabilityQuery) returns (CapabilityResponse);
}

message P2PMessage {
  string from_node = 1;
  string to_node = 2;
  string type = 3;  // "query", "offer", "request", etc
  string payload = 4;  // JSON
  int64 timestamp = 5;
}

message CollaborationRequest {
  string task_id = 1;
  string description = 2;
  repeated string required_capabilities = 3;
  string strategy = 4;  // "parallel", "sequential", "specialist"
}
```

---

### 1.3 Agent Node (Autonomous)

**Objetivo:** Each node é um agente completo

```python
# cluster/agent_node.py

class AgentNode:
    """
    Autonomous agent node with P2P capabilities
    """

    def __init__(self, config):
        self.node_id = config['node_id']
        self.capabilities = config['capabilities']

        # P2P layer
        self.discovery = P2PDiscovery(self.node_id, self.capabilities)
        self.messenger = P2PMessenger(self.node_id, config['address'])

        # Agent logic
        self.task_analyzer = TaskAnalyzer()
        self.decision_engine = DecisionEngine()
        self.subagent_manager = SubAgentManager()

        # State
        self.current_tasks = []
        self.specializations = config.get('specializations', [])

    async def start(self):
        """Start autonomous agent"""

        # 1. Announce presence
        await self.discovery.announce()
        await self.discovery.discover_peers()

        # 2. Start message handler
        asyncio.create_task(self._handle_messages())

        # 3. Start work loop
        asyncio.create_task(self._work_loop())

        logger.info(f"Agent {self.node_id} started in autonomous mode")

    async def receive_task(self, task):
        """
        Receive task from external client or peer
        """

        # Analyze task
        analysis = await self.task_analyzer.analyze(task)

        # Decide strategy
        strategy = await self.decision_engine.choose_strategy(
            task, analysis, self.discovery.peers
        )

        if strategy == "work_alone":
            # I can handle this
            result = await self._execute_locally(task)

        elif strategy == "collaborate":
            # Need help from peers
            result = await self._collaborate_on_task(task, analysis)

        elif strategy == "delegate":
            # Someone else is better suited
            result = await self._delegate_task(task, analysis)

        return result

    async def _execute_locally(self, task):
        """Execute task using local subagents"""

        # Spawn or reuse subagent
        subagent = await self.subagent_manager.get_or_create(
            task_type=task.type,
            required_capabilities=task.capabilities
        )

        # Execute
        result = await subagent.execute(task)

        return result

    async def _collaborate_on_task(self, task, analysis):
        """Collaborate with peers on complex task"""

        # 1. Decompose task
        subtasks = analysis['subtasks']

        # 2. Find suitable peers
        peers = await self._find_collaborators(subtasks)

        # 3. Form team
        team = await self._form_team(peers, subtasks)

        # 4. Coordinate execution
        results = await self._coordinate_team_execution(team)

        # 5. Aggregate results
        final_result = await self._aggregate_results(results)

        return final_result

    async def _find_collaborators(self, subtasks):
        """Find peers that can help with subtasks"""

        collaborators = {}

        for subtask in subtasks:
            # Query network
            responses = await self.messenger.query(
                query_type="can_help",
                criteria={
                    'task_type': subtask.type,
                    'capabilities': subtask.required_capabilities
                }
            )

            # Rank by suitability
            suitable_peers = self._rank_peers(responses, subtask)
            collaborators[subtask.id] = suitable_peers

        return collaborators

    async def _form_team(self, peers, subtasks):
        """Negotiate team formation"""

        team = []

        for subtask_id, suitable_peers in peers.items():
            # Pick best peer
            best_peer = suitable_peers[0]

            # Request collaboration
            response = await self.messenger.send_message(
                best_peer['node_id'],
                {
                    'type': 'collaboration_request',
                    'payload': {
                        'task_id': subtask_id,
                        'description': subtasks[subtask_id].description
                    }
                }
            )

            if response.accepted:
                team.append({
                    'peer': best_peer,
                    'subtask': subtasks[subtask_id]
                })

        return team

    async def _coordinate_team_execution(self, team):
        """Coordinate parallel execution"""

        tasks = []
        for member in team:
            task = asyncio.create_task(
                self._execute_remote_task(member['peer'], member['subtask'])
            )
            tasks.append(task)

        # Wait for all
        results = await asyncio.gather(*tasks)

        return results

    def _rank_peers(self, responses, subtask):
        """Rank peers by suitability"""

        scored = []
        for response in responses:
            score = 0

            # Capability match
            if subtask.required_capabilities in response.capabilities:
                score += 10

            # Specialization bonus
            if subtask.domain in response.specializations:
                score += 5

            # Load factor (prefer less loaded)
            score -= response.current_load * 2

            # Latency factor
            score -= response.latency_ms / 10

            scored.append({
                'node_id': response.node_id,
                'score': score,
                **response
            })

        # Sort by score
        return sorted(scored, key=lambda x: x['score'], reverse=True)
```

---

## 🏗️ Fase 2: Advanced Collaboration (Sprint 3)

### 2.1 Task Decomposition

```python
# cluster/task_analyzer.py

class TaskAnalyzer:
    """
    Analyze tasks and determine execution strategy
    """

    async def analyze(self, task):
        """Deep analysis of task"""

        return {
            'complexity': self._assess_complexity(task),
            'can_decompose': self._can_decompose(task),
            'subtasks': self._decompose(task) if self._can_decompose(task) else [],
            'required_capabilities': self._extract_capabilities(task),
            'domain': self._identify_domain(task),
            'parallelizable': self._is_parallelizable(task),
            'estimated_time': self._estimate_time(task),
            'resource_requirements': self._estimate_resources(task)
        }

    def _can_decompose(self, task):
        """Check if task can be broken down"""

        # Tasks that can be decomposed:
        # - "Process dataset AND generate report"
        # - "Analyze code, find bugs, suggest fixes"
        # - "Translate document to 5 languages"

        indicators = [
            'and' in task.description.lower(),
            'then' in task.description.lower(),
            len(task.description.split()) > 50,
            task.type in ['pipeline', 'batch', 'multi-step']
        ]

        return any(indicators)

    def _decompose(self, task):
        """Break task into subtasks"""

        # Use LLM to decompose
        prompt = f"""
        Break down this task into independent subtasks:

        Task: {task.description}

        Return JSON array of subtasks, each with:
        - id
        - description
        - type
        - required_capabilities
        - dependencies (IDs of other subtasks)
        """

        # Call local LLM
        response = await self.llm.complete(prompt)
        subtasks = json.loads(response)

        return subtasks
```

### 2.2 Decision Engine

```python
# cluster/decision_engine.py

class DecisionEngine:
    """
    Decide how to execute task
    """

    async def choose_strategy(self, task, analysis, available_peers):
        """
        Choose execution strategy:
        - work_alone: Handle locally
        - collaborate: Team up with peers
        - delegate: Send to specialist
        """

        # Scoring system
        scores = {
            'work_alone': 0,
            'collaborate': 0,
            'delegate': 0
        }

        # Factor 1: Can I do it alone?
        if self._have_capabilities(task.required_capabilities):
            scores['work_alone'] += 10

        # Factor 2: Is it complex?
        if analysis['complexity'] > 7:
            scores['collaborate'] += 8

        # Factor 3: Can it be parallelized?
        if analysis['parallelizable']:
            scores['collaborate'] += 5

        # Factor 4: Is there a specialist?
        if self._has_specialist(task.domain, available_peers):
            scores['delegate'] += 7

        # Factor 5: Am I overloaded?
        if len(self.current_tasks) > 5:
            scores['delegate'] += 3
            scores['collaborate'] += 3

        # Factor 6: Privacy concerns?
        if task.metadata.get('privacy') == 'high':
            scores['work_alone'] += 15  # Keep local

        # Choose highest score
        strategy = max(scores, key=scores.get)

        logger.info(f"Chosen strategy: {strategy}", scores=scores)

        return strategy
```

---

## 🏗️ Fase 3: Domain Specialization (Sprint 4)

### 3.1 Learning and Specialization

```python
# cluster/specialization.py

class SpecializationEngine:
    """
    Node learns and specializes over time
    """

    def __init__(self, node_id):
        self.node_id = node_id
        self.domain_history = {}  # {domain: [task_results]}
        self.expertise_scores = {}  # {domain: float}

    async def record_task_completion(self, task, result):
        """Learn from completed task"""

        domain = task.domain

        if domain not in self.domain_history:
            self.domain_history[domain] = []

        self.domain_history[domain].append({
            'task_id': task.id,
            'success': result.success,
            'execution_time': result.execution_time,
            'quality_score': result.quality_score,
            'timestamp': time.time()
        })

        # Update expertise score
        await self._update_expertise(domain)

    async def _update_expertise(self, domain):
        """Calculate expertise score for domain"""

        history = self.domain_history[domain]

        if len(history) < 5:
            # Not enough data
            self.expertise_scores[domain] = 0.3
            return

        # Calculate based on:
        # - Success rate
        # - Speed (compared to baseline)
        # - Quality scores
        # - Recency (recent tasks weighted more)

        recent_tasks = history[-20:]  # Last 20 tasks

        success_rate = sum(1 for t in recent_tasks if t['success']) / len(recent_tasks)
        avg_quality = sum(t['quality_score'] for t in recent_tasks) / len(recent_tasks)

        expertise = (success_rate * 0.5) + (avg_quality * 0.5)

        self.expertise_scores[domain] = expertise

        logger.info(f"Updated expertise for {domain}: {expertise:.2f}")

    async def announce_specialization(self):
        """Announce specialized domains to network"""

        # Find domains where we excel
        specialized_domains = [
            domain for domain, score in self.expertise_scores.items()
            if score > 0.7  # Threshold for "specialist"
        ]

        await self.messenger.broadcast({
            'type': 'specialization_announcement',
            'payload': {
                'node_id': self.node_id,
                'specialized_domains': specialized_domains,
                'expertise_scores': self.expertise_scores
            }
        })
```

---

## 📊 Roadmap Summary

| Sprint | Features | Status |
|--------|----------|--------|
| **Sprint 2** | P2P Discovery, Messaging, Autonomous Node | 🔄 Next |
| **Sprint 3** | Task Decomposition, Collaboration, Team Formation | 📋 Planned |
| **Sprint 4** | Domain Specialization, Learning, Reputation | 📋 Planned |
| **Sprint 5** | Fault Tolerance, Replication, Advanced Coordination | 📋 Planned |

---

## 🧪 Testing Strategy

### Unit Tests
```python
# Test individual components
test_p2p_discovery()
test_p2p_messaging()
test_task_analyzer()
test_decision_engine()
```

### Integration Tests
```python
# Test node interactions
test_two_nodes_collaboration()
test_task_delegation()
test_team_formation()
```

### E2E Tests
```python
# Test full scenarios
test_complex_task_parallelization()
test_specialist_routing()
test_fault_tolerance()
```

---

**Status:** Ready for implementation
**Next:** Sprint 2 kickoff
**Author:** Hudson RJ + Claude
**Date:** 2026-04-21
