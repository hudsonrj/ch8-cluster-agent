# CH8 Agent - Project Overview

## Sobre o Projeto

**CH8 Agent** é um sistema de agentes distribuídos multi-nó com coordenação inteligente. Este projeto permite que múltiplos agentes de IA rodem em máquinas diferentes, compartilhando recursos e interagindo entre si de forma coordenada.

### Características Principais

- **Arquitetura Distribuída**: Agentes rodando em máquinas fisicamente diferentes
- **Agentes Compartilhados**: Múltiplos nós podem compartilhar e interagir com agentes
- **Coordenação Inteligente**: Master coordena tasks entre workers em diferentes máquinas
- **Comunicação via gRPC**: Comunicação eficiente e type-safe entre nós
- **Service Discovery via Redis**: Workers se registram automaticamente
- **Alta Disponibilidade**: Failover automático e health monitoring

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────┐
│                    MASTER NODE                          │
│                  (Máquina Central)                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Master Agent                                   │   │
│  │  - Coordenação global                           │   │
│  │  - Distribuição de tasks                        │   │
│  │  - Agregação de resultados                      │   │
│  └──────────┬──────────────────────────────────────┘   │
│             │ gRPC/Redis Discovery                      │
└─────────────┼─────────────────────────────────────────────┘
              │
      ┌───────┴───────┐              ┌──────────────┐
      │  WORKER 1     │              │  WORKER N    │
      │ (Máquina A)   │              │ (Máquina B)  │
      │ ┌───────────┐ │              │ ┌──────────┐ │
      │ │Agent      │ │              │ │Agent     │ │
      │ │Principal  │ │              │ │Principal │ │
      │ └─────┬─────┘ │              │ └────┬─────┘ │
      │   ┌───┴───┐   │              │  ┌───┴────┐ │
      │   │SubAg 1│   │              │  │SubAg N │ │
      │   └───────┘   │              │  └────────┘ │
      └───────────────┘              └──────────────┘
```

## Componentes Principais

### 1. Master Node (`cluster/master.py`)
- **Responsabilidade**: Coordenador central do cluster
- **Funções**:
  - Aceita tasks de clientes/APIs
  - Analisa requisitos das tasks
  - Roteia tasks para workers apropriados
  - Agrega resultados
  - Mantém health do cluster
- **Comunicação**:
  - gRPC Server na porta 50051 (configurável)
  - Redis para service discovery

### 2. Worker Nodes (`cluster/worker.py`)
- **Responsabilidade**: Executa tasks delegadas pelo master
- **Funções**:
  - Registra-se com master no startup
  - Expõe capabilities via MCP
  - Executa tasks recebidas
  - Reporta resultados ao master
  - Gerencia subagents locais
- **Comunicação**:
  - gRPC Client conecta ao master
  - gRPC Server para receber tasks (porta 50052+)

### 3. Service Discovery (`cluster/discovery.py`)
- **Responsabilidade**: Descoberta e registro de serviços
- **Implementação**: Redis-based
- **Funções**:
  - Workers se auto-registram
  - TTL automático (2x heartbeat interval)
  - Limpeza de workers inativos
  - Busca por capabilities
  - Health monitoring

### 4. Model Manager (`cluster/model_manager.py`)
- **Responsabilidade**: Gerenciamento de modelos de IA
- **Funções**:
  - Seleção inteligente de modelos
  - Roteamento baseado em custo/latência/privacidade
  - Suporte a múltiplos providers (Ollama, OpenRouter, Groq)
  - Balanceamento de carga entre modelos

## Fluxo de Execução

### Task Submission Flow

```
1. Client submete task ao Master
   ↓
2. Master recebe e enfileira task
   ↓
3. Master seleciona Worker apropriado
   - Verifica capabilities
   - Analisa carga atual
   - Considera latência
   ↓
4. Master envia task ao Worker via gRPC
   ↓
5. Worker aceita e executa task
   - Pode spawnar subagents
   - Usa model adequado
   ↓
6. Worker reporta resultado ao Master
   ↓
7. Master armazena resultado
   ↓
8. Client recupera resultado
```

### Worker Registration Flow

```
1. Worker inicia e descobre capabilities locais
   ↓
2. Worker conecta ao Master via gRPC
   ↓
3. Worker registra-se no Redis via Master
   - Envia worker_id
   - Envia capabilities
   - Envia endereço (host:port)
   ↓
4. Master confirma registro
   - Retorna heartbeat interval
   ↓
5. Worker inicia loop de heartbeat
   - Envia status a cada 10s (default)
   - Atualiza métricas (CPU, RAM, tasks ativas)
   ↓
6. Master mantém worker ativo no Redis
   - Renova TTL a cada heartbeat
```

## Configuração

### Master Configuration (`config/master.yaml`)
```yaml
node_id: "master-001"
grpc_port: 50051
discovery:
  redis_url: "redis://:password@host:6379/0"
  heartbeat_interval_seconds: 10
```

### Worker Configuration (`config/worker.yaml`)
```yaml
node_id: "worker-001"
master_url: "grpc://master-host:50051"
grpc_port: 50052
max_concurrent_tasks: 5
models:
  default: "ollama/phi-3-mini"
  available:
    - name: "ollama/phi-3-mini"
      type: "local"
```

## Deployment em Múltiplas Máquinas

### Requisitos por Máquina

**Master Node:**
- Python 3.12+
- Redis Server (ou acesso a Redis remoto)
- 2GB+ RAM
- Porta 50051 acessível

**Worker Nodes:**
- Python 3.12+
- Acesso ao Master via rede
- 4GB+ RAM (dependendo dos modelos)
- Porta 50052+ acessível

### Setup Multi-Machine

1. **Máquina Master:**
```bash
# Instalar dependências
git clone https://github.com/hudsonrj/ch8-agent.git
cd ch8-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar Redis
sudo apt install redis-server
redis-server --requirepass 1q2w3e4r

# Editar config/master.yaml com IP real
vim config/master.yaml
# Mudar redis_url para IP real

# Iniciar Master
python cluster/master.py
```

2. **Máquinas Workers:**
```bash
# Instalar dependências
git clone https://github.com/hudsonrj/ch8-agent.git
cd ch8-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Editar config/worker.yaml
vim config/worker.yaml
# Mudar master_url para IP do Master
# master_url: "grpc://192.168.1.100:50051"

# Iniciar Worker
python cluster/worker.py config/worker.yaml
```

3. **Verificar Conectividade:**
```bash
# No Master, verificar workers registrados
python test-e2e.py
```

### Configuração de Rede

**Portas necessárias:**
- Master: 50051 (gRPC)
- Workers: 50052, 50053, ... (gRPC)
- Redis: 6379

**Firewall:**
```bash
# No Master
sudo ufw allow 50051/tcp
sudo ufw allow 6379/tcp

# Nos Workers
sudo ufw allow 50052/tcp
```

## Casos de Uso

### 1. Processamento Distribuído de Dados
- Master distribui chunks de dados para workers
- Cada worker processa em paralelo
- Master agrega resultados

### 2. Multi-Model Inference
- Workers com diferentes GPUs/modelos
- Master roteia queries ao modelo apropriado
- Balanceamento de carga automático

### 3. Agentes Colaborativos
- Múltiplos agentes trabalhando em sub-tasks
- Compartilhamento de contexto via Master
- Agregação inteligente de resultados

### 4. Fault Tolerance
- Worker falha → Master detecta via heartbeat
- Task é re-roteada para outro worker
- Sistema continua operando

## Tecnologias Utilizadas

| Componente | Tecnologia | Versão |
|------------|------------|--------|
| Runtime | Python | 3.12+ |
| Comunicação | gRPC | 1.60+ |
| Service Discovery | Redis | 5.0+ |
| Serialização | Protocol Buffers | 3.0+ |
| Logging | structlog | 24.1+ |
| Async Runtime | asyncio | stdlib |
| Model Routing | LiteLLM | 1.30+ |

## Roadmap

### Sprint 1 ✅ COMPLETO
- [x] Redis-based service discovery
- [x] Master gRPC server
- [x] Worker gRPC client
- [x] Task assignment end-to-end
- [x] Demo: 1 master + 2 workers localmente

### Sprint 2 (Em Planejamento)
- [ ] HTTP API no Master para submissão de tasks
- [ ] Execução real de modelos (LiteLLM integration)
- [ ] Task retry logic
- [ ] Worker selection melhorado (latência, custo)
- [ ] Multi-machine deployment tested

### Sprint 3 (Futuro)
- [ ] MCP capability registry
- [ ] OpenRAG distribuído
- [ ] WebSocket para streaming results
- [ ] Monitoring (Prometheus + Grafana)

### Sprint 4 (Futuro)
- [ ] Kubernetes deployment
- [ ] Auto-scaling de workers
- [ ] Persistent task queue
- [ ] Authentication/Authorization

## Performance

### Benchmarks Locais (3 processos, mesma máquina)
- Worker registration: < 100ms
- Heartbeat latency: < 10ms
- Task assignment: < 50ms
- Redis operations: < 5ms

### Escalabilidade Estimada
- **Workers por Master**: 100+ (limitado por Redis throughput)
- **Tasks por minuto**: 1000+ (limitado por workers)
- **Latência adicional (rede)**: +10-50ms entre máquinas

## Segurança

### Produção (TODO)
- [ ] TLS para gRPC
- [ ] Redis com authentication (parcialmente implementado)
- [ ] Token-based worker authentication
- [ ] Rate limiting no Master
- [ ] Network isolation (VPN/VPC)

### Desenvolvimento (Atual)
- Redis com senha
- gRPC sem TLS (localhost apenas)
- Sem autenticação de workers

## Troubleshooting

### Worker não registra
```bash
# Verificar conectividade com Master
telnet master-ip 50051

# Verificar logs do Worker
tail -f /tmp/ch8-worker1.log

# Verificar Redis
redis-cli -h master-ip -a 1q2w3e4r SMEMBERS cluster:workers
```

### Tasks não executam
```bash
# Verificar workers ativos
python test-e2e.py

# Ver logs do Master
tail -f /tmp/ch8-master.log

# Verificar capabilities do worker
redis-cli -a 1q2w3e4r GET cluster:worker:worker-001
```

### Latência alta
- Verificar latência de rede entre máquinas
- Considerar deploy workers mais próximos geograficamente
- Aumentar timeout configs em `config/*.yaml`

## Contribuindo

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para guidelines.

## Licença

MIT License - ver [LICENSE](LICENSE)

## Contato

- **Autor**: Hudson RJ
- **GitHub**: [@hudsonrj28](https://github.com/hudsonrj28)
- **Repository**: [ch8-agent](https://github.com/hudsonrj/ch8-agent)

---

**Status Atual**: Sprint 1 completo, funcional em ambiente local.
**Próximo**: Sprint 2 - Multi-machine deployment + Real model execution.
**Última atualização**: 2026-04-20
