# Opções de Instalação - CH8 Agent

## Opção 1: Clone direto do repositório atual

```bash
# O repositório atual ainda se chama ch8-cluster-agent no GitHub
git clone https://github.com/hudsonrj/ch8-cluster-agent.git
cd ch8-agent
```

## Opção 2: Se você renomear o repositório no GitHub

Se você renomear o repositório no GitHub de `ch8-cluster-agent` para `ch8-agent`:

1. Vá para: https://github.com/hudsonrj/ch8-cluster-agent/settings
2. Em "Repository name", mude para `ch8-agent`
3. Clique em "Rename"

Depois disso, o comando de instalação será:

```bash
git clone https://github.com/hudsonrj/ch8-agent.git
cd ch8-agent
```

## Opção 3: Fork com novo nome

Se você quiser fazer um fork com nome diferente:

1. Fork o repositório no GitHub
2. Renomeie seu fork
3. Clone seu fork

```bash
git clone https://github.com/SEU-USUARIO/ch8-agent.git
cd ch8-agent
```

## Após o clone (qualquer opção):

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Instalar e configurar Redis
sudo apt install redis-server  # Ubuntu/Debian
brew install redis             # macOS

# Configurar senha do Redis
redis-cli CONFIG SET requirepass "1q2w3e4r"

# Iniciar o cluster
bash test-cluster.sh
```

---

**Nota:** O nome do diretório local sempre será `ch8-agent` independente do nome no GitHub, pois todos os caminhos internos já foram atualizados.
