# ⚡ Hermes Agent - Quick Reference

**Cheat sheet para comandos e configurações mais comuns.**

---

## 🚀 Comandos Principais

### Iniciar / Parar Cluster

```bash
# Iniciar (script automático)
bash test-cluster.sh

# Parar
bash stop-cluster.sh

# Verificar status
python test-e2e.py

# Enviar tarefa de teste
python test-submit.py
```

### Iniciar Manualmente

```bash
# Terminal 1: Master
python cluster/master.py

# Terminal 2: Worker 1
python cluster/worker.py --config config/worker.yaml

# Terminal 3: Worker 2
python cluster/worker.py --config config/workers/worker-002.yaml
```

### PM2 (Produção)

```bash
# Iniciar tudo
pm2 start ecosystem.config.js

# Status
pm2 status

# Logs
pm2 logs ch8-master
pm2 logs ch8-worker-001

# Restart
pm2 restart ch8-master
pm2 restart all

# Parar
pm2 stop all
pm2 delete all

# Salvar configuração
pm2 save

# Auto-start no boot
pm2 startup
```

### Systemd (Linux)

```bash
# Iniciar
sudo systemctl start ch8-master
sudo systemctl start ch8-worker@001

# Status
sudo systemctl status ch8-master

# Logs
sudo journalctl -u ch8-master -f

# Parar
sudo systemctl stop ch8-master

# Reiniciar
sudo systemctl restart ch8-master

# Habilitar auto-start
sudo systemctl enable ch8-master
```

---

## 🐳 Docker

### Docker Compose

```bash
# Build e iniciar
docker-compose up -d

# Logs
docker-compose logs -f

# Parar
docker-compose down

# Rebuild
docker-compose up -d --build

# Ver containers
docker-compose ps
```

### Docker Manual

```bash
# Build images
docker build -t ch8-master:latest -f Dockerfile.master .
docker build -t ch8-worker:latest -f Dockerfile.worker .

# Run master
docker run -d --name ch8-master \
  -p 50051:50051 \
  -e REDIS_HOST=redis \
  ch8-master:latest

# Run worker
docker run -d --name ch8-worker-001 \
  -e MASTER_HOST=master \
  -e REDIS_HOST=redis \
  ch8-worker:latest
```

---

## 🔍 Verificação e Debug

### Redis

```bash
# Conectar
redis-cli -a 1q2w3e4r

# Ver workers registrados
KEYS cluster:worker:*

# Ver dados de um worker
HGETALL cluster:worker:worker-001

# Monitorar comandos em tempo real
MONITOR

# Flush DB (cuidado!)
FLUSHDB
```

### Logs

```bash
# Master
tail -f logs/master.log

# Worker
tail -f logs/worker-001.log

# Filtrar por task
grep "task-001" logs/*.log

# Ver últimas 50 linhas
tail -50 logs/master.log
```

### Processos

```bash
# Ver processos Python rodando
ps aux | grep python

# Ver específicos do CH8
ps aux | grep -E "master.py|worker.py"

# Kill processo específico
kill <PID>

# Kill todos
pkill -f master.py
pkill -f worker.py
```

### Portas

```bash
# Ver quem está usando porta 50051
sudo lsof -i :50051

# Ver todas as portas do CH8
sudo lsof -i :50051,50052,50053,6379

# Testar conexão
nc -zv localhost 50051
telnet localhost 50051
```

---

## ⚙️ Configuração Rápida

### Worker Config Mínimo

```yaml
# config/worker.yaml
worker:
  name: "worker-001"
  port: 50052

master:
  host: "localhost"
  port: 50051

redis:
  host: "localhost"
  password: "1q2w3e4r"

models:
  default: "ollama/phi3:mini"
```

### Master Config Mínimo

```yaml
# config/master.yaml
master:
  port: 50051

redis:
  host: "localhost"
  password: "1q2w3e4r"

cluster:
  heartbeat_interval: 10
  worker_ttl: 30
```

---

## 🐍 Python API

### Conectar ao Master

```python
import grpc
from protos import cluster_pb2, cluster_pb2_grpc

channel = grpc.insecure_channel('localhost:50051')
stub = cluster_pb2_grpc.MasterServiceStub(channel)
```

### Submeter Tarefa

```python
import json

task = cluster_pb2.TaskAssignment(
    task_id="my-task-001",
    task_type="text_generation",
    payload=json.dumps({
        "prompt": "Hello, world!",
        "max_tokens": 100
    }),
    priority=5
)

response = stub.SubmitTask(task)
print(f"Assigned to: {response.worker_id}")
```

### Verificar Status

```python
status = stub.GetTaskStatus(
    cluster_pb2.TaskStatusRequest(task_id="my-task-001")
)

print(f"Status: {status.status}")  # PENDING, RUNNING, COMPLETED, FAILED
```

### Obter Resultado

```python
result = stub.GetTaskResult(
    cluster_pb2.TaskResultRequest(
        task_id="my-task-001",
        timeout=60
    )
)

if result.success:
    output = json.loads(result.output)
    print(output)
else:
    print(f"Error: {result.error_message}")
```

---

## 🧪 Testes

### Pytest

```bash
# Todos os testes
pytest tests/ -v

# Apenas unit tests
pytest tests/unit/ -v

# Apenas integration tests
pytest tests/integration/ -v

# Com cobertura
pytest tests/ --cov=cluster --cov-report=html

# Ver cobertura
open htmlcov/index.html

# Testes rápidos (skip slow)
pytest tests/ -m "not slow"

# Teste específico
pytest tests/unit/test_discovery.py::test_register_worker -v

# Com output
pytest tests/ -v -s

# Parar no primeiro erro
pytest tests/ -x
```

### Benchmark

```bash
# Latência
python tests/benchmark/bench_latency.py

# Throughput (quando implementado)
python tests/benchmark/bench_throughput.py
```

---

## 📦 Dependências

### Instalar

```bash
# Produção
pip install -r requirements.txt

# Desenvolvimento
pip install -r requirements-dev.txt

# Upgrade all
pip install --upgrade -r requirements.txt
```

### requirements.txt

```
grpcio>=1.59.0
grpcio-tools>=1.59.0
redis>=5.0.0
PyYAML>=6.0
python-dotenv>=1.0.0
psutil>=5.9.0
```

### requirements-dev.txt

```
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-asyncio>=0.21.0
black>=23.9.0
flake8>=6.1.0
isort>=5.12.0
mypy>=1.5.0
```

---

## 🔧 Troubleshooting Rápido

### Worker não se registra

```bash
# 1. Verificar Redis
redis-cli -a 1q2w3e4r PING

# 2. Verificar master rodando
ps aux | grep master.py

# 3. Verificar logs
tail -20 logs/worker-001.log

# 4. Testar conectividade
nc -zv localhost 50051
```

### Redis connection refused

```bash
# Iniciar Redis
sudo systemctl start redis

# Ou Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine redis-server --requirepass 1q2w3e4r
```

### Port already in use

```bash
# Encontrar processo usando porta
sudo lsof -i :50051

# Matar processo
kill <PID>

# Ou mudar porta no config
```

### Out of memory

```yaml
# Reduzir limites em worker.yaml
resources:
  max_concurrent_tasks: 1
  memory_limit_mb: 512

models:
  default: "ollama/gemma:2b"  # Modelo menor
```

---

## 📚 Links Úteis

| Recurso | Link |
|---------|------|
| Manual Completo | [docs/MANUAL.md](docs/MANUAL.md) |
| Deployment | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Testes | [docs/TESTING.md](docs/TESTING.md) |
| Contribuir | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| GitHub Issues | https://github.com/hudsonrj/hermes-agent/issues |

---

## 🎯 Tasks Comuns

### Adicionar novo worker

```bash
# 1. Copiar config
cp config/worker.yaml config/workers/worker-003.yaml

# 2. Editar (mudar name e port)
vim config/workers/worker-003.yaml

# 3. Iniciar
python cluster/worker.py --config config/workers/worker-003.yaml
```

### Mudar modelo do worker

```yaml
# Em worker.yaml
models:
  default: "ollama/llama3:8b"  # Era phi3:mini
```

### Conectar worker remoto

```yaml
# worker.yaml na máquina remota
master:
  host: "192.168.1.100"  # IP do master
  
redis:
  host: "192.168.1.100"
```

### Debug task lenta

```python
# Adicionar logging em worker.py
import time
start = time.time()
result = self.execute_task(payload)
elapsed = time.time() - start
logger.info(f"Task took {elapsed:.2f}s")
```

---

## 🔐 Segurança Básica

```bash
# Redis com senha forte
redis-cli CONFIG SET requirepass "SENHA_FORTE_AQUI"

# Firewall (abrir apenas para rede local)
sudo ufw allow from 192.168.1.0/24 to any port 6379
sudo ufw allow from 192.168.1.0/24 to any port 50051

# SSH seguro
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Fail2ban
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

---

**Quick Reference mantido por:** Hudson RJ + PhiloSophia 🦉  
**Versão:** 0.2.0-alpha  
**Data:** 2026-04-20
