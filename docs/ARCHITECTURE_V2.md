# CH8 Agent - Architecture V2 (Federated Peer-to-Peer)

**Data:** 2026-04-21
**Status:** Proposta de Redesign
**Objetivo:** Arquitetura federada e robusta

---

## 🎯 Visão Revisada

### Problemas da Arquitetura Atual (V1)

**Arquitetura Master-Worker (Centralizada):**
```
    MASTER (single point of failure)
       ↓
  ┌────┴────┐
WORKER  WORKER
```

**Limitações:**
1. ❌ **Single Point of Failure**: Se master cai, cluster para
2. ❌ **Gargalo de comunicação**: Tudo passa pelo master
3. ❌ **Workers passivos**: Não podem tomar decisões sozinhos
4. ❌ **Sem comunicação direta**: Workers não conversam entre si
5. ❌ **Escalabilidade limitada**: Master vira bottleneck

### Nova Visão (V2) - Federação de Agentes

**Arquitetura Peer-to-Peer com Coordenação Opcional:**
```
  NODE 1 ←→ NODE 2 ←→ NODE 3
     ↕         ↕         ↕
  SubAg     SubAg     SubAg
```

**Princípios:**
1. ✅ **Cada nó é um agente principal** autônomo
2. ✅ **Comunicação peer-to-peer** entre nós
3. ✅ **Cada nó gerencia subagentes** locais
4. ✅ **Autonomia**: Pode trabalhar sozinho
5. ✅ **Colaboração**: Pode se unir para tarefas complexas
6. ✅ **Especialização**: Cada nó tem domínios de expertise
7. ✅ **Sem single point of failure**: Totalmente distribuído

---

## 🏗️ Nova Arquitetura Detalhada

### 1. Node Structure (Nó Individual)

```python
class AgentNode:
    """
    Cada nó é um agente principal completo
    """
    def __init__(self):
        # Identidade
        self.node_id = uuid.uuid4()
        self.name = "node-01"
        self.role = "generalist"  # ou "specialist"

        # Capacidades
        self.capabilities = {
            "domains": ["code", "text", "analysis"],
            "models": ["llama-70b", "phi-3"],
            "tools": ["python", "search", "database"],
            "resources": {
                "cpu": 8,
                "ram_gb": 16,
                "gpu": False
            }
        }

        # Subagentes
        self.subagents = []  # Gerenciados localmente

        # Estado
        self.is_autonomous = True  # Pode trabalhar sozinho
        self.current_tasks = []
        self.peer_nodes = {}  # Outros nós conhecidos

        # Comunicação
        self.discovery = P2PDiscovery()  # Peer discovery
        self.messenger = P2PMessenger()  # Peer messaging
```

### 2. Peer-to-Peer Communication

**Protocolo de Comunicação:**

```python
# Tipo de mensagens entre peers
class MessageType:
    # Descoberta
    ANNOUNCE = "announce"        # "Eu existo!"
    QUERY = "query"              # "Quem sabe fazer X?"
    RESPONSE = "response"        # "Eu sei fazer X"

    # Colaboração
    TASK_REQUEST = "task_req"    # "Preciso de ajuda com Y"
    TASK_OFFER = "task_offer"    # "Posso ajudar com Y"
    TASK_ACCEPT = "task_accept"  # "Aceito ajudar"

    # Coordenação
    PROPOSE_TEAM = "team_prop"   # "Vamos formar equipe"
    JOIN_TEAM = "team_join"      # "Entro na equipe"
    TASK_UPDATE = "task_update"  # "Status da minha parte"

    # Especialização
    SHARE_KNOWLEDGE = "knowledge" # "Aprendi algo novo"
    REQUEST_EXPERTISE = "expert"  # "Preciso de especialista em X"
```

**Exemplo de Fluxo:**

```
NODE-1: Recebe tarefa complexa "Analisar dataset e gerar relatório"

NODE-1: Analisa → Tarefa pode ser dividida:
        1. Processamento de dados (pesado)
        2. Análise estatística
        3. Geração de texto

NODE-1: Broadcast QUERY("quem tem GPU?")
NODE-2: RESPONSE("eu tenho GPU + PyTorch")

NODE-1: Broadcast QUERY("quem é especialista em stats?")
NODE-3: RESPONSE("eu sou especialista em estatística")

NODE-1: PROPOSE_TEAM([NODE-1, NODE-2, NODE-3])
NODE-2: JOIN_TEAM(aceita)
NODE-3: JOIN_TEAM(aceita)

# Trabalho paralelo
NODE-2: Processa dados com GPU
NODE-3: Faz análise estatística
NODE-1: Aguarda e depois gera relatório

# Todos reportam status
NODE-2: TASK_UPDATE("processamento 50%...")
NODE-3: TASK_UPDATE("análise completa")

# NODE-1 agrega resultados
NODE-1: Combina outputs e entrega tarefa
```

### 3. Discovery Mechanism

**Gossip Protocol para P2P Discovery:**

```python
class P2PDiscovery:
    """
    Descoberta peer-to-peer sem server central
    """

    async def announce_presence(self):
        """Anuncia presença na rede"""
        message = {
            "type": "announce",
            "node_id": self.node_id,
            "capabilities": self.capabilities,
            "address": self.address,
            "timestamp": time.time()
        }

        # Multicast ou broadcast para descobrir peers
        await self.broadcast(message)

    async def discover_peers(self):
        """Descobre outros nós ativamente"""
        # Opções:
        # 1. mDNS/Bonjour (local network)
        # 2. DHT (distributed hash table)
        # 3. Gossip protocol
        # 4. Redis Pub/Sub (opcional, não obrigatório)

    async def maintain_peer_list(self):
        """Mantém lista de peers ativos"""
        # Remove peers inativos
        # Atualiza capabilities dos peers
        # Prioriza peers por latência/confiabilidade
```

**Vantagens:**
- ✅ Sem single point of failure
- ✅ Auto-organização
- ✅ Resiliente a partições de rede

### 4. Task Distribution Strategies

**Estratégias de Distribuição:**

#### A) Autonomous Mode (Trabalho Solo)
```python
async def work_alone(self, task):
    """
    Nó trabalha sozinho quando:
    - Tarefa é simples
    - Tem todas as capabilities necessárias
    - Quer privacidade/isolamento
    """
    result = await self.execute_with_subagents(task)
    return result
```

#### B) Collaborative Mode (Paralelização)
```python
async def work_collaboratively(self, task):
    """
    Nó recruta peers quando:
    - Tarefa é complexa
    - Pode ser paralelizada
    - Outros têm capabilities complementares
    """

    # 1. Decompor tarefa
    subtasks = await self.decompose_task(task)

    # 2. Encontrar peers adequados
    peers = await self.find_capable_peers(subtasks)

    # 3. Negociar colaboração
    team = await self.form_team(peers, subtasks)

    # 4. Executar em paralelo
    results = await asyncio.gather(*[
        peer.execute(subtask)
        for peer, subtask in team
    ])

    # 5. Agregar resultados
    final_result = await self.aggregate(results)
    return final_result
```

#### C) Specialist Mode (Roteamento por Domínio)
```python
async def delegate_to_specialist(self, task):
    """
    Nó delega quando:
    - Tarefa requer expertise específica
    - Outro nó é mais qualificado
    """

    # 1. Identificar domínio necessário
    required_domain = self.identify_domain(task)

    # 2. Consultar network por especialistas
    specialists = await self.query_specialists(required_domain)

    # 3. Escolher melhor especialista
    best = self.rank_specialists(specialists)

    # 4. Delegar e monitorar
    result = await best.execute(task)
    return result
```

### 5. Coordination Patterns

**Padrões de Coordenação:**

#### Pattern 1: Leader Election (Temporário)
```python
async def elect_leader_for_task(nodes, task):
    """
    Elege líder temporário para coordenar tarefa específica
    - Baseado em quem iniciou a tarefa
    - Ou quem tem mais contexto
    - Liderança é temporária e específica
    """
    leader = max(nodes, key=lambda n: n.relevance_score(task))
    return leader
```

#### Pattern 2: Consensus (Decisão Distribuída)
```python
async def reach_consensus(nodes, decision):
    """
    Nodes votam em decisões importantes
    - Como dividir uma tarefa
    - Qual estratégia usar
    - Como agregar resultados
    """
    votes = await gather_votes(nodes, decision)
    result = majority_vote(votes)
    return result
```

#### Pattern 3: Pipeline (Cadeia de Processamento)
```python
async def pipeline_processing(task):
    """
    Tarefa passa por nodes em sequência
    Cada node adiciona sua expertise
    """
    result = task
    for node in pipeline:
        result = await node.process(result)
    return result
```

### 6. Subagent Management

**Cada nó gerencia seus próprios subagentes:**

```python
class AgentNode:

    async def spawn_subagent(self, task_type):
        """Cria subagente especializado"""
        subagent = SubAgent(
            parent=self,
            specialty=task_type,
            resources=self.allocate_resources()
        )
        self.subagents.append(subagent)
        return subagent

    async def execute_with_subagents(self, task):
        """Usa subagents para executar"""

        # Estratégia 1: Delegar para subagent existente
        if matching_subagent := self.find_subagent(task):
            return await matching_subagent.execute(task)

        # Estratégia 2: Criar novo subagent
        subagent = await self.spawn_subagent(task.type)
        result = await subagent.execute(task)

        # Estratégia 3: Coordenar múltiplos subagents
        if task.is_complex():
            subtasks = self.decompose(task)
            results = await asyncio.gather(*[
                self.get_or_create_subagent(st).execute(st)
                for st in subtasks
            ])
            return self.merge_results(results)
```

---

## 🔧 Implementation Strategy

### Phase 1: Add P2P Layer (Mantém compatibilidade)

```python
class AgentNode:
    """
    Node híbrido: pode ser master, worker ou peer
    """
    def __init__(self, mode="peer"):
        self.mode = mode  # "master", "worker", "peer"

        if mode == "peer":
            # Modo P2P completo
            self.p2p = P2PNetwork()
            self.autonomous = True

        elif mode == "master":
            # Modo legado (backward compat)
            self.master_server = MasterNode()

        elif mode == "worker":
            # Modo legado (backward compat)
            self.worker_client = WorkerNode()
```

### Phase 2: Gradual Migration

**Permitir transição gradual:**

```yaml
# config/node.yaml
node:
  id: "node-001"
  mode: "hybrid"  # Suporta ambos P2P e master-worker

  # P2P settings
  p2p:
    enabled: true
    discovery: "gossip"  # ou "mdns", "dht", "redis"
    port: 50100

  # Legacy master-worker (optional)
  legacy:
    master_url: "grpc://master:50051"  # Se quiser coordenação central

  # Capabilities
  capabilities:
    domains: ["code", "text"]
    models: ["llama-70b"]

  # Specialization
  specialization:
    domains: ["python", "data-analysis"]
    expertise_level: 0.8
```

### Phase 3: Advanced Features

1. **Knowledge Sharing**
   - Nodes compartilham learnings
   - Cache distribuído de resultados
   - Collective memory

2. **Load Balancing Automático**
   - Nodes monitoram carga uns dos outros
   - Auto-rebalanceamento de tasks

3. **Fault Tolerance**
   - Replicação de tasks críticas
   - Automatic failover entre peers

4. **Domain Specialization**
   - Nodes se especializam ao longo do tempo
   - Reputation system por domínio

---

## 📊 Comparison: V1 vs V2

| Aspecto | V1 (Master-Worker) | V2 (P2P Federated) |
|---------|-------------------|-------------------|
| **Single Point of Failure** | ❌ Sim (Master) | ✅ Não |
| **Escalabilidade** | ⚠️ Limitada pelo master | ✅ Linear |
| **Autonomia** | ❌ Workers dependentes | ✅ Cada node é autônomo |
| **Comunicação** | ⚠️ Sempre via master | ✅ Direta entre peers |
| **Latência** | ⚠️ 2 hops (worker→master→worker) | ✅ 1 hop (peer→peer) |
| **Complexidade** | ✅ Simples | ⚠️ Mais complexo |
| **Resiliência** | ❌ Baixa | ✅ Alta |
| **Paralelização** | ⚠️ Coordenada pelo master | ✅ Auto-organizada |
| **Especialização** | ⚠️ Capabilities básicas | ✅ Domínios e expertise |

---

## 🎯 Recommended Architecture

### Hybrid Approach (Melhor dos dois mundos)

```
┌─────────────────────────────────────────┐
│         OPTIONAL COORDINATOR            │  ← Opcional, não crítico
│    (para tasks que precisam orquestração)│
└─────────────────┬───────────────────────┘
                  │ (consulta, não controle)
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼───┐     ┌───▼───┐     ┌───▼───┐
│NODE 1 │ ←→  │NODE 2 │ ←→  │NODE 3 │  ← P2P direto
│Agent  │     │Agent  │     │Agent  │
│+SubAg │     │+SubAg │     │+SubAg │
└───────┘     └───────┘     └───────┘
```

**Características:**
1. ✅ Nodes se comunicam diretamente (P2P)
2. ✅ Cada node é autônomo e pode trabalhar sozinho
3. ✅ Coordinator opcional apenas para orquestração complexa
4. ✅ Se coordinator cai, cluster continua operando
5. ✅ Backward compatible com V1

---

## 🚀 Next Steps

### Sprint 2 (Updated Roadmap)

1. **Implementar P2P Discovery**
   - mDNS para local network
   - Gossip protocol para WAN
   - Mantém Redis como fallback

2. **Peer-to-Peer Messaging**
   - gRPC bidirecional entre peers
   - Protocol Buffers para mensagens

3. **Autonomous Agent Logic**
   - Decision making local
   - Task decomposition
   - Peer recruitment

4. **Hybrid Mode**
   - Suporta V1 (master-worker)
   - Suporta V2 (P2P)
   - Migração gradual

---

**Status:** Proposta para discussão e refinamento
**Autor:** Hudson RJ + Claude
**Data:** 2026-04-21
