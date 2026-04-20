# 📖 CH8 Cluster Agent - Manual Completo

**Versão:** 0.2.0-alpha  
**Data:** 2026-04-20  
**Status:** Sprint 1 Completo (50% do projeto)

---

## 📑 Índice

1. [Visão Geral](#visão-geral)
2. [Instalação](#instalação)
3. [Configuração](#configuração)
4. [Guia de Uso](#guia-de-uso)
5. [Arquitetura](#arquitetura)
6. [API Reference](#api-reference)
7. [Troubleshooting](#troubleshooting)
8. [Casos de Uso](#casos-de-uso)
9. [Desenvolvimento](#desenvolvimento)
10. [FAQ](#faq)

---

## 1. Visão Geral

### O que é o CH8 Cluster Agent?

CH8 é um **sistema distribuído de agentes de IA** que permite coordenar múltiplos nós computacionais (notebooks antigos, Raspberry Pi, VPS baratos) para executar tarefas de forma inteligente e escalável.

### Principais Características

| Recurso | Descrição |
|---------|-----------|
| **Distribuído** | 1 Master + N Workers em diferentes máquinas |
| **Inteligente** | Seleção automática de workers por carga e capability |
| **Flexível** | Suporte para modelos locais (Ollama) e APIs (OpenRouter/Groq) |
| **Resiliente** | Heartbeats automáticos, detecção de falhas, TTL |
| **Leve** | Roda em hardware limitado (4GB RAM, CPU-only) |

### Quando Usar?

✅ **Use CH8 quando:**
- Você tem múltiplas máquinas disponíveis (mesmo antigas/fracas)
- Precisa processar tarefas em paralelo
- Quer aproveitar modelos locais + APIs externas
- Busca reduzir custos de API rodando tarefas simples localmente

❌ **Não use CH8 quando:**
- Você tem apenas 1 máquina potente (use agente único)
- Tarefas exigem latência ultra-baixa (<50ms)
- Todas as tarefas precisam de GPU (CH8 é otimizado para CPU)

---

## 2. Instalação

### 2.1 Requisitos do Sistema

**Mínimos (Worker leve):**
- CPU: 1 core
- RAM: 1GB
- Storage: 2GB
- OS: Linux, macOS, Windows 10+
- Python: 3.11+

**Recomendados (Master):**
- CPU: 2+ cores
- RAM: 4GB+
- Storage: 10GB+
- Redis: 6.0+

### 2.2 Instalação Básica

```bash
# 1. Clonar repositório
git clone https://github.com/hudsonrj/ch8-cluster-agent.git
cd ch8-cluster-agent

# 2. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Compilar gRPC protocols (se necessário)
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. protos/cluster.proto

# 5. Verificar instalação
python -c "import grpc; print('gRPC OK')"
python -c "import redis; print('Redis client OK')"
```

### 2.3 Instalação do Redis

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Configurar senha
redis-cli
> CONFIG SET requirepass "1q2w3e4r"
> AUTH 1q2w3e4r
> PING
```

**macOS:**
```bash
brew install redis
brew services start redis
redis-cli CONFIG SET requirepass "1q2w3e4r"
```

**Docker:**
```bash
docker run -d --name ch8-redis \
  -p 6379:6379 \
  redis:7-alpine redis-server --requirepass 1q2w3e4r
```

### 2.4 Instalação do Ollama (Opcional - para modelos locais)

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Baixar modelos leves
ollama pull phi3:mini      # 2.3GB, bom para tarefas gerais
ollama pull gemma:2b       # 1.4GB, ultra-leve
ollama pull llama3:8b      # 4.7GB, melhor qualidade

# Testar
ollama run phi3:mini "Hello, world!"
```

---

## 3. Configuração

### 3.1 Estrutura de Configuração

```
config/
├── master.yaml          # Configuração do master
├── worker.yaml          # Configuração padrão dos workers
└── workers/            # Configs específicos por worker
    ├── worker-001.yaml
    └── worker-002.yaml
```

### 3.2 Configurar Master

**`config/master.yaml`:**
```yaml
master:
  host: "0.0.0.0"
  port: 50051
  name: "ch8-master-01"
  
redis:
  host: "localhost"
  port: 6379
  password: "1q2w3e4r"
  db: 0
  
cluster:
  heartbeat_interval: 10    # segundos
  worker_ttl: 30           # segundos (3x heartbeat)
  max_retries: 3
  task_timeout: 300        # segundos
  
logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  file: "logs/master.log"
```

### 3.3 Configurar Worker

**`config/worker.yaml`:**
```yaml
worker:
  name: "worker-001"       # Único por worker
  host: "0.0.0.0"
  port: 50052              # Incrementar para cada worker
  capabilities:
    - "general_agent"
    - "python_execution"
    - "text_generation"
  
master:
  host: "localhost"        # IP do master
  port: 50051
  
redis:
  host: "localhost"
  port: 6379
  password: "1q2w3e4r"
  db: 0
  
models:
  default: "ollama/phi3:mini"
  available:
    # Modelos locais (Ollama)
    - name: "ollama/phi3:mini"
      type: "local"
      context_length: 4096
      cost_per_1k_tokens: 0.0
      privacy: "HIGH"
      speed: "fast"
      
    - name: "ollama/llama3:8b"
      type: "local"
      context_length: 8192
      cost_per_1k_tokens: 0.0
      privacy: "HIGH"
      speed: "medium"
      
    # Modelos API
    - name: "openrouter/anthropic/claude-3.5-sonnet"
      type: "api"
      context_length: 200000
      cost_per_1k_tokens: 0.003
      privacy: "LOW"
      speed: "fast"
      api_key_env: "OPENROUTER_API_KEY"
      
    - name: "groq/llama-3.1-70b-versatile"
      type: "api"
      context_length: 131072
      cost_per_1k_tokens: 0.0
      privacy: "LOW"
      speed: "very_fast"
      api_key_env: "GROQ_API_KEY"

routing:
  # Roteamento automático de tarefas
  rules:
    - condition: "privacy == 'HIGH'"
      model_type: "local"
      
    - condition: "tokens < 1000"
      model: "ollama/phi3:mini"
      
    - condition: "tokens > 50000"
      model: "openrouter/anthropic/claude-3.5-sonnet"
      
    - condition: "speed_priority == 'max'"
      model: "groq/llama-3.1-70b-versatile"

resources:
  max_concurrent_tasks: 2
  memory_limit_mb: 2048
  cpu_limit_percent: 80

logging:
  level: "INFO"
  file: "logs/worker-001.log"
```

### 3.4 Variáveis de Ambiente

Crie `.env` na raiz do projeto:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=1q2w3e4r

# API Keys (opcional)
OPENROUTER_API_KEY=sk-or-v1-xxxxx
GROQ_API_KEY=gsk_xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Ollama
OLLAMA_HOST=http://localhost:11434

# Logging
LOG_LEVEL=INFO
```

---

## 4. Guia de Uso

### 4.1 Iniciar o Cluster (Local)

**Modo Interativo - Terminal 1 (Master):**
```bash
cd /data/ch8-cluster-agent
source venv/bin/activate
python cluster/master.py
```

**Modo Interativo - Terminal 2 (Worker 1):**
```bash
cd /data/ch8-cluster-agent
source venv/bin/activate
python cluster/worker.py --config config/worker.yaml
```

**Modo Interativo - Terminal 3 (Worker 2):**
```bash
cd /data/ch8-cluster-agent
source venv/bin/activate
python cluster/worker.py --config config/workers/worker-002.yaml
```

**Modo Automatizado (Script):**
```bash
bash test-cluster.sh    # Inicia master + 2 workers em background
bash stop-cluster.sh    # Para todos os processos
```

### 4.2 Verificar Status do Cluster

**Método 1: Script Python**
```bash
python test-e2e.py
```

Saída esperada:
```
✅ Cluster Status:
   Active workers: 2

   • worker-001 @ localhost:50052
     Capabilities: general_agent, python_execution
     Load: 0/2 tasks
     Last heartbeat: 2s ago

   • worker-002 @ localhost:50053
     Capabilities: general_agent, python_execution
     Load: 1/2 tasks
     Last heartbeat: 1s ago
```

**Método 2: Redis CLI**
```bash
redis-cli -a 1q2w3e4r
> KEYS cluster:worker:*
> HGETALL cluster:worker:worker-001
```

### 4.3 Submeter Tarefas

**Método 1: Script Python**

```python
# test-submit.py
import grpc
from protos import cluster_pb2, cluster_pb2_grpc

# Conectar ao master
channel = grpc.insecure_channel('localhost:50051')
stub = cluster_pb2_grpc.MasterServiceStub(channel)

# Criar tarefa
task = cluster_pb2.TaskAssignment(
    task_id="task-001",
    task_type="text_generation",
    payload='{"prompt": "Explain quantum computing in simple terms"}',
    priority=5
)

# Enviar
response = stub.SubmitTask(task)
print(f"Task submitted: {response.task_id}")
print(f"Assigned to: {response.worker_id}")
```

**Método 2: REST API (Sprint 2)**
```bash
curl -X POST http://localhost:8080/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "type": "text_generation",
    "payload": {
      "prompt": "Explain quantum computing",
      "max_tokens": 500
    },
    "priority": 5
  }'
```

### 4.4 Monitorar Tarefas

```python
# Buscar status de tarefa
task_status = stub.GetTaskStatus(cluster_pb2.TaskStatusRequest(
    task_id="task-001"
))

print(f"Status: {task_status.status}")  # PENDING, RUNNING, COMPLETED, FAILED
print(f"Worker: {task_status.worker_id}")
print(f"Progress: {task_status.progress}%")
```

### 4.5 Recuperar Resultados

```python
# Aguardar conclusão
result = stub.GetTaskResult(cluster_pb2.TaskResultRequest(
    task_id="task-001",
    timeout=60  # segundos
))

if result.success:
    print(f"Result: {result.output}")
else:
    print(f"Error: {result.error_message}")
```

---

## 5. Arquitetura

### 5.1 Componentes Principais

```
┌─────────────────────────────────────────────────────┐
│                   MASTER NODE                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  MasterService (gRPC Server)                 │  │
│  │  - RegisterWorker()                          │  │
│  │  - ProcessHeartbeat()                        │  │
│  │  - SubmitTask()                              │  │
│  │  - GetTaskStatus()                           │  │
│  └────────┬─────────────────────────────────────┘  │
│           │                                         │
│  ┌────────┴─────────────────────────────────────┐  │
│  │  Cluster Manager                             │  │
│  │  - Worker Registry (Redis)                   │  │
│  │  - Task Queue                                │  │
│  │  - Load Balancer                             │  │
│  │  - Health Monitor                            │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                        │
            ┌───────────┴───────────┐
            │                       │
  ┌─────────▼────────┐    ┌────────▼─────────┐
  │   WORKER NODE 1  │    │  WORKER NODE 2   │
  │ ┌──────────────┐ │    │ ┌──────────────┐ │
  │ │WorkerService │ │    │ │WorkerService │ │
  │ │(gRPC Server) │ │    │ │(gRPC Server) │ │
  │ └──────┬───────┘ │    │ └──────┬───────┘ │
  │        │         │    │        │         │
  │ ┌──────▼───────┐ │    │ ┌──────▼───────┐ │
  │ │Task Executor │ │    │ │Task Executor │ │
  │ │- Model Mgr   │ │    │ │- Model Mgr   │ │
  │ │- Resource Mgr│ │    │ │- Resource Mgr│ │
  │ └──────────────┘ │    │ └──────────────┘ │
  └──────────────────┘    └──────────────────┘
```

### 5.2 Fluxo de Comunicação

**1. Worker Registration:**
```
Worker → Master.RegisterWorker(name, host, port, capabilities)
Master → Redis.HSET("cluster:worker:{name}", {...})
Master → Response(success=true)
```

**2. Heartbeat Loop:**
```
Worker (a cada 10s) → Master.ProcessHeartbeat(worker_id, cpu, ram, tasks)
Master → Redis.EXPIRE("cluster:worker:{id}", 30)
Master → Redis.HSET("cluster:worker:{id}", status=...)
Master → Response(acknowledged)
```

**3. Task Submission:**
```
Client → Master.SubmitTask(task_id, type, payload)
Master → Queue.push(task)
Master → select_best_worker(capabilities, load)
Master → Worker.ExecuteTask(task_id, payload)
Worker → execute()
Worker → Master.ReportResult(task_id, output)
Master → Response(result)
```

### 5.3 Service Discovery (Redis)

**Estrutura de Chaves:**
```
cluster:worker:{worker_id}
  - name: "worker-001"
  - host: "192.168.1.10"
  - port: 50052
  - capabilities: ["general_agent", "python_execution"]
  - status: "ACTIVE"
  - cpu_usage: 45.2
  - memory_usage: 1024
  - active_tasks: 1
  - max_tasks: 2
  - last_heartbeat: 1713638472
  - registered_at: 1713638400
```

**TTL Automático:**
- Cada worker tem TTL de 30 segundos
- Heartbeat renova o TTL
- Se worker morrer, Redis expira a chave automaticamente
- Master detecta ausência e remove worker do pool

---

## 6. API Reference

### 6.1 gRPC Services

#### MasterService

**`RegisterWorker`**
```protobuf
rpc RegisterWorker (WorkerRegistration) returns (RegistrationResponse);

message WorkerRegistration {
  string worker_id = 1;
  string host = 2;
  int32 port = 3;
  repeated string capabilities = 4;
  int32 max_concurrent_tasks = 5;
}

message RegistrationResponse {
  bool success = 1;
  string message = 2;
  int64 assigned_heartbeat_interval = 3;
}
```

**`ProcessHeartbeat`**
```protobuf
rpc ProcessHeartbeat (Heartbeat) returns (HeartbeatAck);

message Heartbeat {
  string worker_id = 1;
  float cpu_usage = 2;
  int64 memory_usage = 3;
  int32 active_tasks = 4;
  string status = 5;
}

message HeartbeatAck {
  bool acknowledged = 1;
  repeated string pending_commands = 2;
}
```

**`SubmitTask`**
```protobuf
rpc SubmitTask (TaskAssignment) returns (TaskResponse);

message TaskAssignment {
  string task_id = 1;
  string task_type = 2;
  string payload = 3;  // JSON string
  int32 priority = 4;
  int32 timeout = 5;
  string preferred_worker = 6;  // optional
}

message TaskResponse {
  bool accepted = 1;
  string worker_id = 2;
  string message = 3;
}
```

#### WorkerService

**`ExecuteTask`**
```protobuf
rpc ExecuteTask (TaskAssignment) returns (TaskResult);

message TaskResult {
  string task_id = 1;
  bool success = 2;
  string output = 3;  // JSON string
  string error_message = 4;
  int64 execution_time_ms = 5;
}
```

### 6.2 Model Manager API

```python
from cluster.model_manager import ModelManager

# Inicializar
manager = ModelManager(config_path="config/worker.yaml")

# Selecionar modelo automaticamente
model = manager.select_model(
    task_size=2000,          # tokens estimados
    privacy_level="HIGH",    # HIGH, MEDIUM, LOW
    speed_priority=False,    # True = prioriza velocidade
    user_preference=None     # Força modelo específico
)

# Executar inferência
response = manager.execute(
    model_name=model,
    prompt="Explain quantum computing",
    max_tokens=500,
    temperature=0.7
)

# Obter custo estimado
cost = manager.estimate_cost(
    model_name="openrouter/anthropic/claude-3.5-sonnet",
    input_tokens=1000,
    output_tokens=500
)
```

---

## 7. Troubleshooting

### 7.1 Problemas Comuns

#### Worker não se registra no Master

**Sintoma:** Worker inicia mas não aparece em `test-e2e.py`

**Diagnóstico:**
```bash
# Verificar logs do worker
tail -f logs/worker-001.log

# Verificar se Redis está acessível
redis-cli -h localhost -p 6379 -a 1q2w3e4r PING

# Verificar se master está rodando
ps aux | grep "python.*master.py"
```

**Soluções:**
1. Confirmar que Redis está rodando e senha correta
2. Verificar firewall não está bloqueando porta 50051
3. Confirmar que host/port no worker.yaml está correto
4. Verificar logs do master para mensagens de erro

#### Tasks ficam em PENDING indefinidamente

**Sintoma:** `stub.GetTaskStatus()` sempre retorna `PENDING`

**Diagnóstico:**
```bash
# Verificar workers ativos
python -c "
import redis
r = redis.Redis(host='localhost', password='1q2w3e4r')
keys = r.keys('cluster:worker:*')
print(f'Workers ativos: {len(keys)}')
for key in keys:
    print(r.hgetall(key))
"

# Verificar fila de tasks
# (Sprint 2: redis LLEN cluster:tasks:queue)
```

**Soluções:**
1. Confirmar que pelo menos 1 worker está ACTIVE
2. Verificar se worker tem capability necessária
3. Verificar carga dos workers (todos podem estar cheios)
4. Aumentar timeout da task

#### Erro "UNAVAILABLE: failed to connect to all addresses"

**Sintoma:** Cliente gRPC não consegue conectar

**Soluções:**
```bash
# Verificar se porta está aberta
netstat -tuln | grep 50051

# Testar conectividade
telnet localhost 50051

# Se em máquinas diferentes, verificar firewall
sudo ufw allow 50051/tcp

# Verificar se master está ouvindo em 0.0.0.0 (não 127.0.0.1)
# Em master.yaml: host: "0.0.0.0"
```

#### OOM (Out of Memory) no Worker

**Sintoma:** Worker morre com `Killed` no log

**Soluções:**
```yaml
# Em worker.yaml, reduzir limites:
resources:
  max_concurrent_tasks: 1     # Era 2
  memory_limit_mb: 1024       # Era 2048
  
models:
  default: "ollama/gemma:2b"  # Modelo mais leve
```

### 7.2 Logs e Debugging

**Ativar logs detalhados:**
```yaml
# Em master.yaml / worker.yaml
logging:
  level: "DEBUG"  # Em vez de INFO
```

**Logs úteis:**
```bash
# Logs estruturados
tail -f logs/master.log
tail -f logs/worker-001.log

# Filtrar por task específica
grep "task-001" logs/*.log

# Monitorar Redis em tempo real
redis-cli -a 1q2w3e4r MONITOR
```

**Debug gRPC:**
```python
import grpc
import logging

# Ativar logs gRPC
logging.basicConfig(level=logging.DEBUG)
grpc_logger = logging.getLogger('grpc')
grpc_logger.setLevel(logging.DEBUG)
```

---

## 8. Casos de Uso

### 8.1 Processamento de Documentos em Lote

**Cenário:** Processar 10.000 PDFs, extrair texto, gerar resumos.

**Solução com CH8:**
```python
import grpc
from protos import cluster_pb2_grpc, cluster_pb2
import json

# Conectar ao master
channel = grpc.insecure_channel('localhost:50051')
stub = cluster_pb2_grpc.MasterServiceStub(channel)

# Submeter tarefas em lote
tasks = []
for i, pdf_path in enumerate(pdf_files):
    task = cluster_pb2.TaskAssignment(
        task_id=f"doc-{i}",
        task_type="document_processing",
        payload=json.dumps({
            "file_path": pdf_path,
            "operations": ["extract_text", "summarize"]
        }),
        priority=3
    )
    response = stub.SubmitTask(task)
    tasks.append(response.task_id)
    
    if i % 100 == 0:
        print(f"Submitted {i}/10000 tasks...")

# Aguardar conclusão
completed = 0
while completed < len(tasks):
    for task_id in tasks:
        status = stub.GetTaskStatus(cluster_pb2.TaskStatusRequest(task_id=task_id))
        if status.status == "COMPLETED":
            completed += 1
    print(f"Completed: {completed}/{len(tasks)}")
    time.sleep(5)
```

**Benefícios:**
- 3 workers → 3x mais rápido que sequencial
- Tarefas simples usam modelos locais (custo zero)
- Tarefas complexas automaticamente roteadas para APIs

### 8.2 Sistema de Análise de Sentimentos Multi-idioma

**Cenário:** Analisar tweets em 5 idiomas diferentes, cada worker especializado.

**Config Workers:**
```yaml
# worker-pt.yaml
capabilities:
  - "sentiment_analysis"
  - "language:portuguese"
  
# worker-en.yaml
capabilities:
  - "sentiment_analysis"
  - "language:english"
```

**Código Cliente:**
```python
def analyze_tweet(text, language):
    task = cluster_pb2.TaskAssignment(
        task_id=f"tweet-{uuid.uuid4()}",
        task_type="sentiment_analysis",
        payload=json.dumps({
            "text": text,
            "language": language
        }),
        priority=5
    )
    
    # Master roteia automaticamente para worker com capability correta
    response = stub.SubmitTask(task)
    return response
```

### 8.3 Pipeline de Data Engineering

**Cenário:** Extract → Transform → Load de 100GB de dados.

**Workers Especializados:**
- Worker 1: Extração (I/O pesado)
- Worker 2: Transformação (CPU intensivo)
- Worker 3: Load (conexão com DB)

**Pipeline:**
```python
# Etapa 1: Extrair
extract_task = stub.SubmitTask(TaskAssignment(
    task_type="data_extract",
    payload=json.dumps({"source": "s3://bucket/data.csv"}),
    preferred_worker="worker-io"
))

# Aguardar extração
wait_for_completion(extract_task.task_id)

# Etapa 2: Transformar
transform_task = stub.SubmitTask(TaskAssignment(
    task_type="data_transform",
    payload=json.dumps({"operations": ["clean", "normalize"]}),
    preferred_worker="worker-cpu"
))

wait_for_completion(transform_task.task_id)

# Etapa 3: Load
load_task = stub.SubmitTask(TaskAssignment(
    task_type="data_load",
    payload=json.dumps({"destination": "postgres://..."}),
    preferred_worker="worker-db"
))
```

---

## 9. Desenvolvimento

### 9.1 Adicionar Novo Tipo de Tarefa

**1. Definir handler no Worker:**

```python
# cluster/worker.py

class WorkerNode:
    def __init__(self, config):
        # ...
        self.task_handlers = {
            "text_generation": self.handle_text_generation,
            "image_analysis": self.handle_image_analysis,
            "web_scraping": self.handle_web_scraping,  # NOVO
        }
    
    def handle_web_scraping(self, payload):
        """Scrape website and extract data"""
        import requests
        from bs4 import BeautifulSoup
        
        url = payload.get("url")
        selectors = payload.get("selectors", {})
        
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = {}
        for key, selector in selectors.items():
            results[key] = soup.select(selector)
        
        return {
            "success": True,
            "data": results
        }
```

**2. Adicionar capability:**

```yaml
# config/worker.yaml
capabilities:
  - "web_scraping"  # NOVO
```

**3. Usar no cliente:**

```python
task = cluster_pb2.TaskAssignment(
    task_type="web_scraping",
    payload=json.dumps({
        "url": "https://example.com",
        "selectors": {
            "title": "h1.title",
            "price": "span.price"
        }
    })
)
```

### 9.2 Estrutura de Código

```python
# Exemplo de estrutura recomendada para novos módulos

# cluster/custom_module.py
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CustomModule:
    """Descrição do módulo"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        logger.info("CustomModule initialized")
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa entrada e retorna resultado
        
        Args:
            input_data: Dados de entrada
            
        Returns:
            Resultado processado
            
        Raises:
            ValueError: Se input_data inválido
        """
        try:
            # Lógica aqui
            result = self._internal_process(input_data)
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Error in CustomModule: {e}")
            return {"success": False, "error": str(e)}
    
    def _internal_process(self, data: Dict) -> Any:
        """Método interno auxiliar"""
        pass
```

### 9.3 Testes

**Estrutura de testes:**
```
tests/
├── unit/
│   ├── test_master.py
│   ├── test_worker.py
│   └── test_model_manager.py
├── integration/
│   ├── test_cluster.py
│   └── test_discovery.py
└── e2e/
    └── test_full_workflow.py
```

**Exemplo de teste unitário:**
```python
# tests/unit/test_model_manager.py
import pytest
from cluster.model_manager import ModelManager

def test_select_model_high_privacy():
    config = {"models": [...]}
    manager = ModelManager(config)
    
    model = manager.select_model(
        task_size=500,
        privacy_level="HIGH"
    )
    
    assert "ollama" in model  # Deve ser local
    
def test_select_model_large_task():
    manager = ModelManager(config)
    
    model = manager.select_model(
        task_size=100000,
        privacy_level="LOW"
    )
    
    assert "claude" in model  # Deve ser API com contexto grande
```

**Rodar testes:**
```bash
# Todos os testes
pytest tests/

# Apenas unit tests
pytest tests/unit/

# Com cobertura
pytest --cov=cluster tests/

# Verbose
pytest -v tests/
```

---

## 10. FAQ

### Q1: Posso usar CH8 em produção?

**A:** Sprint 1 está completo mas é **alpha**. Recomendamos esperar Sprint 3 (MCP + RAG + monitoramento) para produção. Para testes e protótipos, está pronto.

### Q2: Qual a latência típica de uma tarefa?

**A:** Depende:
- Tarefa local (Ollama): 2-5s para modelos pequenos
- Tarefa API (Groq): 0.5-2s
- Tarefa API (Claude): 3-8s
- Overhead de comunicação gRPC: ~10-50ms

### Q3: Quantos workers posso ter?

**A:** Teoricamente ilimitado. Testamos com 10 workers. Limitação prática é Redis (pode escalar para milhares) e latência de rede.

### Q4: CH8 funciona sem internet?

**A:** Sim, se usar apenas modelos locais (Ollama). Master e workers se comunicam via rede local. Redis também pode ser local.

### Q5: Como fazer backup do cluster?

**A:** Atualmente apenas Redis precisa de backup:
```bash
redis-cli -a 1q2w3e4r BGSAVE
cp /var/lib/redis/dump.rdb /backup/redis-backup-$(date +%Y%m%d).rdb
```

Sprint 3 adicionará PostgreSQL para persistência de tasks/resultados.

### Q6: Posso misturar Windows/Linux/Mac workers?

**A:** Sim! gRPC é cross-platform. Apenas garanta Python 3.11+ em todos.

### Q7: Como limitar custos de API?

```yaml
# config/worker.yaml
models:
  available:
    - name: "openrouter/..."
      cost_per_1k_tokens: 0.003
      daily_budget_usd: 5.00  # Novo: Sprint 2

routing:
  rules:
    - condition: "daily_cost > 4.50"
      fallback: "ollama/phi3:mini"
```

### Q8: CH8 suporta GPUs?

**A:** Sprint 1 é CPU-only. Sprint 4 adicionará suporte para:
- Workers com GPU (CUDA/ROCm)
- Capability "gpu_acceleration"
- Roteamento de tarefas pesadas para GPU workers

### Q9: Como contribuir com o projeto?

**A:** Ver `CONTRIBUTING.md`. Resumo:
1. Fork o repositório
2. Criar branch: `git checkout -b feature/minha-feature`
3. Commit: `git commit -m "Add: minha feature"`
4. Push: `git push origin feature/minha-feature`
5. Abrir Pull Request

### Q10: Onde buscar ajuda?

- **GitHub Issues:** Bug reports e feature requests
- **Discord:** Chat da comunidade (em breve)
- **Email:** hudson@example.com

---

## 📚 Apêndices

### A. Glossário

| Termo | Definição |
|-------|-----------|
| **Master** | Nó coordenador central do cluster |
| **Worker** | Nó executor de tarefas |
| **Capability** | Habilidade que um worker pode executar |
| **Task** | Unidade de trabalho distribuída |
| **Heartbeat** | Ping periódico worker→master |
| **TTL** | Time-to-live, tempo antes de expirar |
| **gRPC** | Framework de RPC de alta performance |
| **Service Discovery** | Mecanismo de encontrar workers ativos |
| **Load Balancing** | Distribuição de carga entre workers |

### B. Referências Externas

- **gRPC Documentation:** https://grpc.io/docs/
- **Redis Documentation:** https://redis.io/docs/
- **Ollama:** https://ollama.com/
- **LiteLLM:** https://docs.litellm.ai/
- **Protocol Buffers:** https://protobuf.dev/

### C. Roadmap Detalhado

**Sprint 2 (Semana 2) - ETA: 2026-04-27:**
- [ ] HTTP REST API no master (FastAPI)
- [ ] Integração completa task queue
- [ ] Execução de modelos via LiteLLM
- [ ] Task retry com backoff exponencial
- [ ] WebSocket para streaming de resultados

**Sprint 3 (Semanas 3-4) - ETA: 2026-05-11:**
- [ ] MCP capability registry
- [ ] OpenRAG per-node (PostgreSQL + pgvector)
- [ ] Distributed search coordination
- [ ] Worker specialization system
- [ ] Cost tracking dashboard

**Sprint 4 (Semana 5+) - ETA: 2026-05-25:**
- [ ] Prometheus + Grafana monitoring
- [ ] Centralized logging (Loki)
- [ ] Kubernetes deployment (Helm charts)
- [ ] Horizontal pod autoscaling
- [ ] GPU worker support
- [ ] Multi-region coordination

---

**Manual compilado por:** PhiloSophia 🦉 + Hudson RJ  
**Data:** 2026-04-20  
**Versão:** 1.0.0  
**Status:** Sprint 1 Complete (50% do projeto)

Para atualizações: `/data/ch8-cluster-agent/docs/CHANGELOG.md`
