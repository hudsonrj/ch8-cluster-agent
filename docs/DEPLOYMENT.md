# 🚀 CH8 Distributed Agent - Guia de Deployment

**Versão:** 0.2.0-alpha  
**Data:** 2026-04-20

---

## 📑 Índice

1. [Deployment Local](#1-deployment-local)
2. [Deployment em Raspberry Pi](#2-deployment-em-raspberry-pi)
3. [Deployment Multi-Máquina](#3-deployment-multi-máquina)
4. [Deployment em VPS](#4-deployment-em-vps)
5. [Docker](#5-docker)
6. [Kubernetes](#6-kubernetes-sprint-4)
7. [Monitoramento](#7-monitoramento-sprint-3)
8. [Segurança](#8-segurança)

---

## 1. Deployment Local

### 1.1 Máquina Única (Desenvolvimento)

**Requisitos:**
- Ubuntu 20.04+ / macOS 12+ / Windows 10+
- Python 3.11+
- 4GB RAM
- 10GB disk

**Instalação:**
```bash
git clone https://github.com/hudsonrj/ch8-distributed-agent.git
cd ch8-distributed-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Instalar Redis
sudo apt install redis-server  # Ubuntu
brew install redis             # macOS

# Configurar Redis
redis-cli CONFIG SET requirepass "1q2w3e4r"
```

**Iniciar:**
```bash
# Terminal 1: Master
python cluster/master.py

# Terminal 2: Worker 1
python cluster/worker.py --config config/worker.yaml

# Terminal 3: Worker 2
python cluster/worker.py --config config/workers/worker-002.yaml
```

**Automatizado (PM2):**
```bash
# Instalar PM2
npm install -g pm2

# Criar ecosystem
cat > ecosystem.config.js << 'EOF'
module.exports = {
  apps: [
    {
      name: 'ch8-master',
      script: 'venv/bin/python',
      args: 'cluster/master.py',
      cwd: '/data/ch8-distributed-agent',
      autorestart: true,
      max_memory_restart: '1G'
    },
    {
      name: 'ch8-worker-001',
      script: 'venv/bin/python',
      args: 'cluster/worker.py --config config/worker.yaml',
      cwd: '/data/ch8-distributed-agent',
      autorestart: true,
      max_memory_restart: '2G'
    },
    {
      name: 'ch8-worker-002',
      script: 'venv/bin/python',
      args: 'cluster/worker.py --config config/workers/worker-002.yaml',
      cwd: '/data/ch8-distributed-agent',
      autorestart: true,
      max_memory_restart: '2G'
    }
  ]
};
EOF

# Iniciar
pm2 start ecosystem.config.js

# Salvar para auto-start
pm2 save
pm2 startup
```

**Systemd (Linux):**
```bash
# Master service
sudo tee /etc/systemd/system/ch8-master.service > /dev/null << 'EOF'
[Unit]
Description=CH8 Master Node
After=network.target redis.service

[Service]
Type=simple
User=ch8
WorkingDirectory=/opt/ch8-distributed-agent
Environment="PATH=/opt/ch8-distributed-agent/venv/bin"
ExecStart=/opt/ch8-distributed-agent/venv/bin/python cluster/master.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Worker service
sudo tee /etc/systemd/system/ch8-worker@.service > /dev/null << 'EOF'
[Unit]
Description=CH8 Worker Node %i
After=network.target redis.service ch8-master.service

[Service]
Type=simple
User=ch8
WorkingDirectory=/opt/ch8-distributed-agent
Environment="PATH=/opt/ch8-distributed-agent/venv/bin"
ExecStart=/opt/ch8-distributed-agent/venv/bin/python cluster/worker.py --config config/workers/worker-%i.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Habilitar e iniciar
sudo systemctl enable ch8-master
sudo systemctl enable ch8-worker@001
sudo systemctl enable ch8-worker@002
sudo systemctl start ch8-master
sudo systemctl start ch8-worker@001
sudo systemctl start ch8-worker@002

# Verificar status
sudo systemctl status ch8-master
sudo systemctl status ch8-worker@001
```

---

## 2. Deployment em Raspberry Pi

### 2.1 Raspberry Pi 4 (4GB RAM)

**Preparação:**
```bash
# 1. Instalar Raspberry Pi OS Lite (64-bit)
# 2. Configurar SSH
sudo raspi-config  # Interface Options → SSH → Enable

# 3. Atualizar sistema
sudo apt update && sudo apt upgrade -y

# 4. Instalar dependências
sudo apt install -y python3-pip python3-venv redis-server git

# 5. Aumentar swap (recomendado para 4GB RAM)
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

**Instalação CH8:**
```bash
cd /opt
sudo git clone https://github.com/hudsonrj/ch8-distributed-agent.git
sudo chown -R pi:pi ch8-distributed-agent
cd ch8-distributed-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configurar Redis
sudo sed -i 's/# requirepass.*/requirepass 1q2w3e4r/' /etc/redis/redis.conf
sudo systemctl restart redis
```

**Configuração Worker Leve:**
```yaml
# config/pi-worker.yaml
worker:
  name: "pi-worker-001"
  host: "0.0.0.0"
  port: 50052
  capabilities:
    - "general_agent"
    - "lightweight_tasks"

master:
  host: "192.168.1.100"  # IP do master (outra máquina)
  port: 50051

redis:
  host: "192.168.1.100"
  port: 6379
  password: "1q2w3e4r"

models:
  default: "ollama/gemma:2b"  # Modelo ultra-leve
  available:
    - name: "ollama/gemma:2b"
      type: "local"
      context_length: 8192
      cost_per_1k_tokens: 0.0
      privacy: "HIGH"

resources:
  max_concurrent_tasks: 1      # Apenas 1 tarefa por vez
  memory_limit_mb: 1536        # Deixar ~2GB para sistema
  cpu_limit_percent: 70        # Não sobrecarregar

logging:
  level: "INFO"
  file: "/var/log/ch8/worker.log"
```

**Instalar Ollama no Pi:**
```bash
# Método 1: Binário ARM64
curl -fsSL https://ollama.com/install.sh | sh

# Método 2: Docker (se preferir)
docker run -d --name ollama \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --restart always \
  ollama/ollama:latest

# Baixar modelo leve
ollama pull gemma:2b  # 1.4GB
```

**Systemd Service:**
```bash
sudo tee /etc/systemd/system/ch8-pi-worker.service > /dev/null << 'EOF'
[Unit]
Description=CH8 Worker on Raspberry Pi
After=network.target redis.service

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/ch8-distributed-agent
Environment="PATH=/opt/ch8-distributed-agent/venv/bin"
ExecStart=/opt/ch8-distributed-agent/venv/bin/python cluster/worker.py --config config/pi-worker.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable ch8-pi-worker
sudo systemctl start ch8-pi-worker
```

**Monitoramento:**
```bash
# CPU/RAM
htop

# Temperatura (Pi throttles em 80°C)
vcgencmd measure_temp

# Logs
sudo journalctl -u ch8-pi-worker -f
```

---

## 3. Deployment Multi-Máquina

### 3.1 Topologia

```
┌─────────────────────────┐
│  Desktop (Master)       │
│  - Ubuntu 22.04         │
│  - 16GB RAM             │
│  - IP: 192.168.1.100    │
│  - Redis: 6379          │
│  - Master: 50051        │
└────────┬────────────────┘
         │
    ┌────┴──────────┬──────────────┬────────────┐
    │               │              │            │
┌───▼────┐     ┌───▼────┐    ┌───▼────┐  ┌───▼────┐
│Notebook│     │Notebook│    │  Pi 4  │  │  VPS   │
│Worker 1│     │Worker 2│    │Worker 3│  │Worker 4│
│2GB RAM │     │4GB RAM │    │4GB RAM │  │1GB RAM │
│:50052  │     │:50052  │    │:50052  │  │:50052  │
└────────┘     └────────┘    └────────┘  └────────┘
```

### 3.2 Configuração de Rede

**Master (192.168.1.100):**
```yaml
# config/master.yaml
master:
  host: "0.0.0.0"  # Ouvir em todas interfaces
  port: 50051

redis:
  host: "0.0.0.0"  # Redis acessível externamente
  port: 6379
  password: "1q2w3e4r"
  bind: "0.0.0.0"  # Adicionar ao redis.conf
```

**Redis Config:**
```bash
# Editar /etc/redis/redis.conf no master
sudo sed -i 's/bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf
sudo sed -i 's/# requirepass.*/requirepass 1q2w3e4r/' /etc/redis/redis.conf
sudo systemctl restart redis

# Abrir firewall
sudo ufw allow 6379/tcp
sudo ufw allow 50051/tcp
```

**Worker Remoto (192.168.1.101):**
```yaml
# config/remote-worker.yaml
worker:
  name: "notebook-worker-001"
  host: "0.0.0.0"
  port: 50052

master:
  host: "192.168.1.100"  # IP do master
  port: 50051

redis:
  host: "192.168.1.100"  # Redis do master
  port: 6379
  password: "1q2w3e4r"
```

**Testar Conectividade:**
```bash
# Do worker, testar acesso ao master
nc -zv 192.168.1.100 50051  # gRPC
nc -zv 192.168.1.100 6379   # Redis

# Testar Redis
redis-cli -h 192.168.1.100 -p 6379 -a 1q2w3e4r PING
```

### 3.3 Segurança em Rede Local

**Firewall Básico:**
```bash
# No master
sudo ufw allow from 192.168.1.0/24 to any port 6379
sudo ufw allow from 192.168.1.0/24 to any port 50051
sudo ufw enable
```

**Redis com TLS (Opcional):**
```bash
# Gerar certificados
openssl req -x509 -nodes -newkey rsa:4096 \
  -keyout redis.key -out redis.crt -days 365

# Configurar Redis
sudo tee -a /etc/redis/redis.conf > /dev/null << EOF
tls-port 6380
port 0
tls-cert-file /etc/redis/redis.crt
tls-key-file /etc/redis/redis.key
tls-ca-cert-file /etc/redis/ca.crt
EOF

# Worker usa porta 6380 com SSL
redis:
  host: "192.168.1.100"
  port: 6380
  password: "1q2w3e4r"
  ssl: true
  ssl_cert_reqs: "required"
```

---

## 4. Deployment em VPS

### 4.1 VPS Barato ($5/mês, 1GB RAM)

**Providers Recomendados:**
- DigitalOcean: Droplet Basic ($4/mo)
- Linode: Nanode 1GB ($5/mo)
- Vultr: Cloud Compute ($2.50/mo)
- Hetzner: CX11 (€3.29/mo)

**Setup:**
```bash
# 1. Criar VPS Ubuntu 22.04
# 2. SSH inicial
ssh root@<VPS_IP>

# 3. Criar usuário
adduser ch8
usermod -aG sudo ch8
su - ch8

# 4. Instalar deps
sudo apt update
sudo apt install -y python3-pip python3-venv git

# 5. Clonar repo
cd ~
git clone https://github.com/hudsonrj/ch8-distributed-agent.git
cd ch8-distributed-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Config Worker VPS (sem Ollama):**
```yaml
# config/vps-worker.yaml
worker:
  name: "vps-worker-001"
  host: "0.0.0.0"
  port: 50052
  capabilities:
    - "api_proxy"
    - "lightweight_tasks"

master:
  host: "HOME_PUBLIC_IP"  # Seu IP público ou domínio
  port: 50051

redis:
  host: "HOME_PUBLIC_IP"
  port: 6379
  password: "1q2w3e4r"

models:
  default: "groq/llama-3.1-8b-instant"  # Sem modelo local
  available:
    - name: "groq/llama-3.1-8b-instant"
      type: "api"
      context_length: 8192
      cost_per_1k_tokens: 0.0
      api_key_env: "GROQ_API_KEY"
    - name: "openrouter/meta-llama/llama-3-8b-instruct:free"
      type: "api"
      cost_per_1k_tokens: 0.0

resources:
  max_concurrent_tasks: 1
  memory_limit_mb: 512  # Deixar 512MB para sistema
```

**Túnel Reverso (se master em rede privada):**

Opção 1: Cloudflare Tunnel
```bash
# No master (casa)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
./cloudflared tunnel --url localhost:50051 --hostname ch8-master.exemplo.com

# No worker (VPS), usar hostname público
master:
  host: "ch8-master.exemplo.com"
```

Opção 2: ngrok
```bash
# No master
ngrok tcp 50051

# Pegar URL: tcp://0.tcp.ngrok.io:12345
# No worker
master:
  host: "0.tcp.ngrok.io"
  port: 12345
```

---

## 5. Docker

### 5.1 Master Container

**Dockerfile.master:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Deps
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY cluster/ ./cluster/
COPY protos/ ./protos/
COPY config/master.yaml ./config/

# Compilar gRPC
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. protos/cluster.proto

EXPOSE 50051

CMD ["python", "cluster/master.py"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass 1q2w3e4r
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  master:
    build:
      context: .
      dockerfile: Dockerfile.master
    ports:
      - "50051:50051"
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      - REDIS_PASSWORD=1q2w3e4r
    restart: unless-stopped

  worker-001:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - MASTER_HOST=master
      - REDIS_HOST=redis
      - WORKER_NAME=worker-001
      - WORKER_PORT=50052
    depends_on:
      - master
      - redis
    restart: unless-stopped

  worker-002:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - MASTER_HOST=master
      - REDIS_HOST=redis
      - WORKER_NAME=worker-002
      - WORKER_PORT=50053
    depends_on:
      - master
      - redis
    restart: unless-stopped

volumes:
  redis_data:
```

**Rodar:**
```bash
docker-compose up -d
docker-compose logs -f
docker-compose ps
```

### 5.2 Worker Container

**Dockerfile.worker:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Deps
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Ollama (opcional)
RUN curl -fsSL https://ollama.com/install.sh | sh

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY cluster/ ./cluster/
COPY protos/ ./protos/
COPY config/worker.yaml ./config/

# Compilar gRPC
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. protos/cluster.proto

# Pull modelo leve
RUN ollama serve & sleep 5 && ollama pull gemma:2b && pkill ollama

EXPOSE 50052

CMD ["python", "cluster/worker.py", "--config", "config/worker.yaml"]
```

---

## 6. Kubernetes (Sprint 4)

**Estrutura (planejada):**
```
k8s/
├── namespace.yaml
├── master/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
├── worker/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── hpa.yaml
└── redis/
    ├── statefulset.yaml
    └── service.yaml
```

---

## 7. Monitoramento (Sprint 3)

**Prometheus + Grafana (planejado):**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'ch8-master'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'ch8-workers'
    static_configs:
      - targets: ['worker1:9091', 'worker2:9091']
```

---

## 8. Segurança

### 8.1 Checklist

- [ ] Redis com senha forte
- [ ] Firewall configurado (UFW/iptables)
- [ ] SSH com chave pública (sem senha)
- [ ] Usuário não-root para serviços
- [ ] TLS em gRPC (Sprint 2)
- [ ] Logs auditáveis
- [ ] Rate limiting em APIs
- [ ] Secrets em `.env` (não comitar)

### 8.2 Hardening Básico

```bash
# SSH seguro
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Fail2ban
sudo apt install fail2ban
sudo systemctl enable fail2ban

# Atualizações automáticas
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

**Documentado por:** PhiloSophia 🦉  
**Data:** 2026-04-20  
**Versão:** 1.0.0
