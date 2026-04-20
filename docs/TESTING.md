# 🧪 CH8 Distributed Agent - Guia de Testes

**Versão:** 0.2.0-alpha  
**Data:** 2026-04-20

---

## 📋 Índice

1. [Testes Rápidos](#testes-rápidos)
2. [Testes Unitários](#testes-unitários)
3. [Testes de Integração](#testes-de-integração)
4. [Testes End-to-End](#testes-end-to-end)
5. [Benchmark](#benchmark)
6. [Troubleshooting de Testes](#troubleshooting)

---

## 1. Testes Rápidos

### 1.1 Smoke Test (2 minutos)

**Verifica que o cluster está funcionando basicamente:**

```bash
cd /data/ch8-distributed-agent

# 1. Iniciar cluster
bash test-cluster.sh

# 2. Aguardar 5 segundos
sleep 5

# 3. Validar status
python test-e2e.py

# 4. Enviar 1 tarefa
python test-submit.py

# 5. Parar cluster
bash stop-cluster.sh
```

**Resultado esperado:**
```
✅ Master running on localhost:50051
✅ 2 workers registered
✅ Task submitted and completed
✅ All tests passed
```

### 1.2 Health Check

```bash
# Verificar processos rodando
ps aux | grep -E "master.py|worker.py" | grep -v grep

# Verificar Redis
redis-cli -a 1q2w3e4r PING  # Deve retornar PONG

# Verificar workers no Redis
redis-cli -a 1q2w3e4r KEYS "cluster:worker:*"

# Verificar logs recentes
tail -20 logs/master.log
tail -20 logs/worker-001.log
```

---

## 2. Testes Unitários

### 2.1 Estrutura

```
tests/unit/
├── test_discovery.py       # Service discovery
├── test_master.py          # Master logic
├── test_worker.py          # Worker logic
├── test_model_manager.py   # Model selection
└── conftest.py            # Fixtures compartilhados
```

### 2.2 Rodar Testes Unitários

```bash
# Instalar pytest
pip install pytest pytest-cov pytest-asyncio

# Rodar todos os testes
pytest tests/unit/ -v

# Rodar teste específico
pytest tests/unit/test_discovery.py::test_register_worker -v

# Com cobertura
pytest tests/unit/ --cov=cluster --cov-report=html

# Ver cobertura
open htmlcov/index.html
```

### 2.3 Exemplo: Testar Service Discovery

**`tests/unit/test_discovery.py`:**
```python
import pytest
import redis
from cluster.discovery import ServiceDiscovery

@pytest.fixture
def redis_client():
    """Redis client para testes"""
    client = redis.Redis(host='localhost', password='1q2w3e4r', db=15)
    yield client
    # Cleanup
    client.flushdb()

@pytest.fixture
def discovery(redis_client):
    """Discovery service"""
    return ServiceDiscovery(redis_client)

def test_register_worker(discovery):
    """Testa registro de worker"""
    worker_info = {
        "worker_id": "test-worker-001",
        "host": "localhost",
        "port": 50052,
        "capabilities": ["general_agent"]
    }
    
    success = discovery.register_worker(worker_info)
    assert success is True
    
    # Verificar se foi registrado
    workers = discovery.get_active_workers()
    assert len(workers) == 1
    assert workers[0]["worker_id"] == "test-worker-001"

def test_worker_ttl_expiration(discovery):
    """Testa se worker expira após TTL"""
    worker_info = {
        "worker_id": "test-worker-ttl",
        "host": "localhost",
        "port": 50053
    }
    
    # Registrar com TTL curto
    discovery.register_worker(worker_info, ttl=1)
    
    # Verificar que existe
    workers = discovery.get_active_workers()
    assert len(workers) == 1
    
    # Aguardar expiração
    import time
    time.sleep(2)
    
    # Verificar que expirou
    workers = discovery.get_active_workers()
    assert len(workers) == 0

def test_heartbeat_renews_ttl(discovery):
    """Testa que heartbeat renova TTL"""
    worker_id = "test-worker-heartbeat"
    
    # Registrar
    discovery.register_worker({
        "worker_id": worker_id,
        "host": "localhost",
        "port": 50054
    }, ttl=3)
    
    # Aguardar 2s (menos que TTL)
    import time
    time.sleep(2)
    
    # Renovar com heartbeat
    discovery.process_heartbeat(worker_id, {
        "cpu_usage": 50.0,
        "memory_usage": 1024
    })
    
    # Aguardar mais 2s
    time.sleep(2)
    
    # Worker deve ainda existir (total 4s, mas TTL foi renovado)
    workers = discovery.get_active_workers()
    assert len(workers) == 1

def test_get_workers_by_capability(discovery):
    """Testa busca por capability"""
    # Registrar workers com capabilities diferentes
    discovery.register_worker({
        "worker_id": "worker-python",
        "capabilities": ["python_execution", "general_agent"]
    })
    
    discovery.register_worker({
        "worker_id": "worker-js",
        "capabilities": ["javascript_execution", "general_agent"]
    })
    
    # Buscar por capability específica
    python_workers = discovery.get_workers_by_capability("python_execution")
    assert len(python_workers) == 1
    assert python_workers[0]["worker_id"] == "worker-python"
    
    # Buscar por capability comum
    general_workers = discovery.get_workers_by_capability("general_agent")
    assert len(general_workers) == 2
```

### 2.4 Exemplo: Testar Model Manager

**`tests/unit/test_model_manager.py`:**
```python
import pytest
from cluster.model_manager import ModelManager

@pytest.fixture
def manager():
    config = {
        "default": "ollama/phi3:mini",
        "available": [
            {
                "name": "ollama/phi3:mini",
                "type": "local",
                "cost_per_1k_tokens": 0.0,
                "privacy": "HIGH"
            },
            {
                "name": "groq/llama-3.1-70b",
                "type": "api",
                "cost_per_1k_tokens": 0.0,
                "privacy": "LOW"
            }
        ]
    }
    return ModelManager(config)

def test_select_model_high_privacy(manager):
    """Tasks privadas devem usar modelo local"""
    model = manager.select_model(
        task_size=500,
        privacy_level="HIGH"
    )
    assert "ollama" in model

def test_select_model_speed_priority(manager):
    """Speed priority deve escolher Groq"""
    model = manager.select_model(
        task_size=500,
        privacy_level="LOW",
        speed_priority=True
    )
    assert "groq" in model

def test_estimate_cost(manager):
    """Testa cálculo de custo"""
    cost = manager.estimate_cost(
        model_name="groq/llama-3.1-70b",
        input_tokens=1000,
        output_tokens=500
    )
    # Groq é gratuito
    assert cost == 0.0
```

---

## 3. Testes de Integração

### 3.1 Testar Master + Redis

**`tests/integration/test_master_redis.py`:**
```python
import pytest
import grpc
from protos import cluster_pb2, cluster_pb2_grpc
import redis
import subprocess
import time

@pytest.fixture(scope="module")
def redis_client():
    client = redis.Redis(host='localhost', password='1q2w3e4r', db=14)
    client.flushdb()
    yield client
    client.flushdb()

@pytest.fixture(scope="module")
def master_process(redis_client):
    """Inicia master para testes"""
    proc = subprocess.Popen([
        "python", "cluster/master.py",
        "--redis-db", "14"
    ])
    time.sleep(3)  # Aguardar inicialização
    yield proc
    proc.terminate()
    proc.wait()

def test_master_accepts_registration(master_process):
    """Testa que master aceita registro de worker"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    response = stub.RegisterWorker(cluster_pb2.WorkerRegistration(
        worker_id="integration-test-worker",
        host="localhost",
        port=50099,
        capabilities=["test_capability"]
    ))
    
    assert response.success is True
    assert response.assigned_heartbeat_interval > 0

def test_master_persists_to_redis(master_process, redis_client):
    """Testa que master salva worker no Redis"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    worker_id = "redis-persist-test"
    stub.RegisterWorker(cluster_pb2.WorkerRegistration(
        worker_id=worker_id,
        host="localhost",
        port=50098
    ))
    
    # Verificar no Redis
    key = f"cluster:worker:{worker_id}"
    assert redis_client.exists(key) == 1
    
    worker_data = redis_client.hgetall(key)
    assert worker_data[b'host'] == b'localhost'
    assert int(worker_data[b'port']) == 50098
```

### 3.2 Testar Worker + Master

**`tests/integration/test_worker_master.py`:**
```python
def test_worker_registers_on_startup(master_process):
    """Testa que worker se registra ao iniciar"""
    # Iniciar worker
    worker_proc = subprocess.Popen([
        "python", "cluster/worker.py",
        "--config", "config/test-worker.yaml"
    ])
    time.sleep(3)
    
    try:
        # Verificar se está registrado
        channel = grpc.insecure_channel('localhost:50051')
        stub = cluster_pb2_grpc.MasterServiceStub(channel)
        
        # TODO: Adicionar método GetWorkers no master
        # workers = stub.GetWorkers()
        # assert len(workers) > 0
        
        # Por ora, verificar no Redis
        r = redis.Redis(host='localhost', password='1q2w3e4r', db=14)
        keys = r.keys("cluster:worker:*")
        assert len(keys) > 0
    finally:
        worker_proc.terminate()
        worker_proc.wait()

def test_worker_sends_heartbeats(master_process):
    """Testa que worker envia heartbeats"""
    worker_proc = subprocess.Popen([
        "python", "cluster/worker.py",
        "--config", "config/test-worker.yaml"
    ])
    time.sleep(5)
    
    try:
        # Verificar timestamp de último heartbeat no Redis
        r = redis.Redis(host='localhost', password='1q2w3e4r', db=14)
        keys = r.keys("cluster:worker:*")
        
        if keys:
            worker_data = r.hgetall(keys[0])
            last_hb = int(worker_data.get(b'last_heartbeat', 0))
            
            # Aguardar próximo heartbeat
            time.sleep(12)  # Heartbeat a cada 10s
            
            worker_data = r.hgetall(keys[0])
            new_hb = int(worker_data.get(b'last_heartbeat', 0))
            
            assert new_hb > last_hb
    finally:
        worker_proc.terminate()
        worker_proc.wait()
```

---

## 4. Testes End-to-End

### 4.1 Fluxo Completo de Tarefa

**`tests/e2e/test_full_workflow.py`:**
```python
import pytest
import subprocess
import time
import grpc
import json
from protos import cluster_pb2, cluster_pb2_grpc

@pytest.fixture(scope="module")
def cluster():
    """Inicia cluster completo"""
    # Iniciar master
    master = subprocess.Popen(["python", "cluster/master.py"])
    time.sleep(3)
    
    # Iniciar 2 workers
    worker1 = subprocess.Popen([
        "python", "cluster/worker.py",
        "--config", "config/worker.yaml"
    ])
    worker2 = subprocess.Popen([
        "python", "cluster/worker.py",
        "--config", "config/workers/worker-002.yaml"
    ])
    time.sleep(5)
    
    yield {
        "master": master,
        "workers": [worker1, worker2]
    }
    
    # Cleanup
    for proc in [master, worker1, worker2]:
        proc.terminate()
        proc.wait()

def test_submit_and_complete_task(cluster):
    """Testa submissão e execução completa de tarefa"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    # Submeter tarefa
    task = cluster_pb2.TaskAssignment(
        task_id="e2e-test-001",
        task_type="text_generation",
        payload=json.dumps({
            "prompt": "Say hello",
            "max_tokens": 10
        }),
        priority=5
    )
    
    response = stub.SubmitTask(task)
    assert response.accepted is True
    assert response.worker_id != ""
    
    # Aguardar conclusão (polling)
    max_wait = 60
    elapsed = 0
    completed = False
    
    while elapsed < max_wait:
        status = stub.GetTaskStatus(cluster_pb2.TaskStatusRequest(
            task_id="e2e-test-001"
        ))
        
        if status.status == "COMPLETED":
            completed = True
            break
        elif status.status == "FAILED":
            pytest.fail(f"Task failed: {status.error_message}")
        
        time.sleep(2)
        elapsed += 2
    
    assert completed, "Task did not complete in time"
    
    # Verificar resultado
    result = stub.GetTaskResult(cluster_pb2.TaskResultRequest(
        task_id="e2e-test-001"
    ))
    
    assert result.success is True
    assert len(result.output) > 0

def test_parallel_tasks(cluster):
    """Testa execução paralela de múltiplas tarefas"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    # Submeter 10 tarefas
    task_ids = []
    for i in range(10):
        task = cluster_pb2.TaskAssignment(
            task_id=f"parallel-{i}",
            task_type="text_generation",
            payload=json.dumps({"prompt": f"Task {i}"}),
            priority=5
        )
        response = stub.SubmitTask(task)
        task_ids.append(task.task_id)
    
    # Aguardar todas completarem
    start_time = time.time()
    completed = 0
    
    while completed < 10 and (time.time() - start_time) < 120:
        for task_id in task_ids:
            status = stub.GetTaskStatus(cluster_pb2.TaskStatusRequest(
                task_id=task_id
            ))
            if status.status == "COMPLETED":
                completed += 1
        time.sleep(1)
    
    elapsed = time.time() - start_time
    
    # Com 2 workers, deve ser ~5x mais rápido que sequencial
    # (assumindo ~10s por task sequencial = 100s total)
    # Com paralelização: ~50-60s
    assert completed == 10
    assert elapsed < 90, f"Parallel execution too slow: {elapsed}s"

def test_worker_failure_handling(cluster):
    """Testa comportamento quando worker falha"""
    # TODO: Implementar em Sprint 2
    # - Matar 1 worker
    # - Verificar que tarefas são redirecionadas
    # - Verificar que master detecta falha via TTL
    pass
```

---

## 5. Benchmark

### 5.1 Latência de Comunicação

**`tests/benchmark/bench_latency.py`:**
```python
import grpc
import time
from protos import cluster_pb2, cluster_pb2_grpc
import statistics

def benchmark_registration_latency(iterations=100):
    """Mede latência de registro de worker"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    latencies = []
    
    for i in range(iterations):
        start = time.time()
        response = stub.RegisterWorker(cluster_pb2.WorkerRegistration(
            worker_id=f"bench-worker-{i}",
            host="localhost",
            port=50000 + i
        ))
        end = time.time()
        
        latencies.append((end - start) * 1000)  # ms
    
    print(f"Registration Latency:")
    print(f"  Mean: {statistics.mean(latencies):.2f}ms")
    print(f"  Median: {statistics.median(latencies):.2f}ms")
    print(f"  P95: {sorted(latencies)[int(0.95 * len(latencies))]:.2f}ms")
    print(f"  P99: {sorted(latencies)[int(0.99 * len(latencies))]:.2f}ms")

def benchmark_heartbeat_latency(iterations=100):
    """Mede latência de heartbeat"""
    channel = grpc.insecure_channel('localhost:50051')
    stub = cluster_pb2_grpc.MasterServiceStub(channel)
    
    # Registrar worker primeiro
    stub.RegisterWorker(cluster_pb2.WorkerRegistration(
        worker_id="bench-worker-hb",
        host="localhost",
        port=50099
    ))
    
    latencies = []
    
    for i in range(iterations):
        start = time.time()
        response = stub.ProcessHeartbeat(cluster_pb2.Heartbeat(
            worker_id="bench-worker-hb",
            cpu_usage=50.0,
            memory_usage=1024,
            active_tasks=0
        ))
        end = time.time()
        
        latencies.append((end - start) * 1000)
    
    print(f"Heartbeat Latency:")
    print(f"  Mean: {statistics.mean(latencies):.2f}ms")
    print(f"  Median: {statistics.median(latencies):.2f}ms")
    print(f"  P95: {sorted(latencies)[int(0.95 * len(latencies))]:.2f}ms")

if __name__ == "__main__":
    print("Running benchmarks...")
    print()
    benchmark_registration_latency()
    print()
    benchmark_heartbeat_latency()
```

**Rodar:**
```bash
# Iniciar cluster
bash test-cluster.sh

# Rodar benchmark
python tests/benchmark/bench_latency.py

# Resultados esperados:
# Registration: ~10-30ms
# Heartbeat: ~5-15ms
```

### 5.2 Throughput

**`tests/benchmark/bench_throughput.py`:**
```python
def benchmark_task_throughput(num_workers=2, duration_seconds=60):
    """Mede quantas tarefas/segundo o cluster processa"""
    # Iniciar cluster programaticamente
    # Submeter tarefas continuamente por duration_seconds
    # Contar quantas completaram
    # Calcular tasks/segundo
    
    # TODO: Implementar
    pass
```

---

## 6. Troubleshooting de Testes

### Problema: Testes falham com "Connection refused"

**Solução:**
```bash
# Verificar se master está rodando
ps aux | grep master.py

# Se não estiver, iniciar
python cluster/master.py &

# Aguardar 3s antes de rodar testes
sleep 3
pytest tests/
```

### Problema: Redis "NOAUTH Authentication required"

**Solução:**
```python
# Em conftest.py ou nos testes, sempre autenticar:
redis_client = redis.Redis(
    host='localhost',
    password='1q2w3e4r',  # Sempre incluir senha
    db=15  # Usar DB separado para testes
)
```

### Problema: Testes lentos

**Otimizações:**
```bash
# Rodar em paralelo (requer pytest-xdist)
pip install pytest-xdist
pytest tests/ -n 4  # 4 processos paralelos

# Pular testes lentos no desenvolvimento
pytest tests/ -m "not slow"

# Marcar testes lentos:
@pytest.mark.slow
def test_long_running():
    pass
```

### Problema: Fixtures não limpam corretamente

**Solução:**
```python
@pytest.fixture
def my_fixture():
    # Setup
    resource = create_resource()
    
    yield resource
    
    # Cleanup SEMPRE executado (mesmo se teste falhar)
    try:
        resource.cleanup()
    except Exception as e:
        print(f"Cleanup error: {e}")
```

---

## 📊 Cobertura de Código

**Meta:** ≥80% cobertura

```bash
# Gerar relatório de cobertura
pytest tests/ --cov=cluster --cov-report=html --cov-report=term

# Ver no navegador
open htmlcov/index.html

# Falhar se cobertura < 80%
pytest tests/ --cov=cluster --cov-fail-under=80
```

---

**Documentado por:** PhiloSophia 🦉  
**Data:** 2026-04-20  
**Versão:** 1.0.0
