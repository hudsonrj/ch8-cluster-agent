# Instalação do CH8 Agent

## 🚀 Instalação Automática (Recomendado)

Execute o script de instalação automática:

```bash
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash
```

Este script irá:
- ✅ Verificar Python 3.11+
- ✅ Verificar/instalar Redis
- ✅ Clonar o repositório
- ✅ Criar ambiente virtual
- ✅ Instalar dependências
- ✅ Configurar Redis
- ✅ Criar scripts auxiliares
- ✅ (Opcional) Adicionar aliases ao shell

## 📦 Instalação Manual

### 1. Clonar Repositório

```bash
git clone https://github.com/hudsonrj/ch8-cluster-agent.git ch8-agent
cd ch8-agent
```

### 2. Criar Ambiente Virtual

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Instalar Dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Instalar Redis

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install redis-server
```

**macOS:**
```bash
brew install redis
```

**Windows:**
Baixe de: https://github.com/microsoftarchive/redis/releases

### 5. Configurar Redis

```bash
redis-cli CONFIG SET requirepass "1q2w3e4r"
```

Ou edite `/etc/redis/redis.conf`:
```conf
requirepass 1q2w3e4r
```

### 6. Iniciar Redis

**Linux:**
```bash
sudo systemctl start redis
# ou
redis-server &
```

**macOS:**
```bash
brew services start redis
# ou
redis-server &
```

## ✅ Verificar Instalação

```bash
# Testar cluster
bash test-cluster.sh

# Em outro terminal: executar testes
python test-e2e.py
python test-submit.py

# Parar cluster
bash stop-cluster.sh
```

## 🔧 Comandos Úteis (se instalou via script automático)

Se você adicionou os aliases durante a instalação:

```bash
ch8-start    # Iniciar cluster
ch8-test     # Executar testes
ch8-stop     # Parar cluster
ch8-cd       # Ir para diretório de instalação
```

## 🌐 Instalação Multi-Máquina

Para instalar em múltiplas máquinas e criar um cluster distribuído:

### Máquina Master (Coordenador)

```bash
# Instalar
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash

# Configurar
cd ~/ch8-agent
vim config/master.yaml
# Altere redis_url para IP real da máquina
# Exemplo: redis://:1q2w3e4r@192.168.1.100:6379/0

# Abrir portas no firewall
sudo ufw allow 50051/tcp  # gRPC Master
sudo ufw allow 6379/tcp   # Redis

# Iniciar
redis-server &
python cluster/master.py
```

### Máquinas Worker (Executores)

```bash
# Instalar em cada máquina worker
curl -fsSL https://raw.githubusercontent.com/hudsonrj/ch8-cluster-agent/main/scripts/install.sh | bash

# Configurar
cd ~/ch8-agent
vim config/worker.yaml
# Altere master_url para IP do Master
# Exemplo: grpc://192.168.1.100:50051

# Abrir porta no firewall
sudo ufw allow 50052/tcp  # gRPC Worker (50053 para worker 2, etc)

# Iniciar
python cluster/worker.py config/worker.yaml
```

## 🐳 Instalação via Docker (Em breve)

```bash
docker pull hudsonrj/ch8-agent:latest
docker-compose up -d
```

## 🔍 Troubleshooting

### Python não encontrado
```bash
# Ubuntu/Debian
sudo apt-get install python3.11 python3.11-venv

# macOS
brew install python@3.11
```

### Redis não conecta
```bash
# Verificar se está rodando
redis-cli ping
# Deve retornar: PONG

# Verificar porta
sudo netstat -tlnp | grep 6379

# Verificar logs
tail -f /var/log/redis/redis-server.log
```

### Erro de permissão
```bash
# Dar permissão aos scripts
chmod +x *.sh scripts/*.sh

# Problemas com venv
rm -rf venv
python3 -m venv venv
```

## 📚 Próximos Passos

Após a instalação:

1. **Ler documentação:**
   - `README.md` - Visão geral
   - `PROJECT_OVERVIEW.md` - Arquitetura completa
   - `docs/MANUAL.md` - Manual detalhado

2. **Configurar cluster:**
   - Editar `config/master.yaml`
   - Editar `config/worker.yaml`

3. **Testar localmente:**
   ```bash
   bash test-cluster.sh
   python test-e2e.py
   ```

4. **Deploy em produção:**
   - Ver `docs/DEPLOYMENT.md`

## 🆘 Ajuda

- **Issues:** https://github.com/hudsonrj/ch8-cluster-agent/issues
- **Documentação:** `/docs`
- **Exemplos:** `/examples`

---

**Autor:** Hudson RJ ([@hudsonrj28](https://github.com/hudsonrj28))
**Projeto:** CH8 Agent - Distributed Multi-Node System
