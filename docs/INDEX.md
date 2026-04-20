# 📚 Índice de Documentação - CH8 Agent

**Versão:** 0.2.0-alpha  
**Atualizado:** 2026-04-20

---

## 📖 Documentos Principais

### Para Começar

1. **[README.md](../README.md)** (5.8KB)
   - Visão geral do projeto
   - Quick start (5 minutos)
   - Roadmap e status atual
   - Links para documentação

2. **[MANUAL.md](MANUAL.md)** (27KB) 📘
   - **Documento mais completo**
   - 10 seções: instalação, configuração, uso, arquitetura, API, troubleshooting, casos de uso, desenvolvimento, FAQ
   - Recomendado para todos os usuários

3. **[DEPLOYMENT.md](DEPLOYMENT.md)** (14KB)
   - Guia de deployment completo
   - Deployment local, Raspberry Pi, multi-máquina, VPS
   - Docker, Kubernetes (Sprint 4)
   - Monitoramento e segurança

### Desenvolvimento

4. **[TESTING.md](TESTING.md)** (18KB)
   - Testes rápidos (smoke test)
   - Testes unitários com pytest
   - Testes de integração
   - Testes end-to-end
   - Benchmark de latência e throughput

5. **[CONTRIBUTING.md](../CONTRIBUTING.md)** (9.4KB)
   - Como contribuir com o projeto
   - Código de conduta
   - Estilo de código (PEP 8 + Black)
   - Conventional commits
   - Pull request process

### Referência

6. **[architecture.md](architecture.md)** (resumo da arquitetura)
   - Componentes principais
   - Fluxos de comunicação
   - Service discovery
   - Decisões de design

7. **[model-selection.md](model-selection.md)** (7.3KB)
   - Sistema de seleção de modelos
   - Roteamento automático
   - Privacy levels
   - Cost tracking
   - Configuração YAML

8. **[decisions.md](decisions.md)**
   - Decisões técnicas documentadas
   - Rationale para escolhas arquiteturais
   - Trade-offs considerados

### Outros

9. **[CHANGELOG.md](../CHANGELOG.md)** (4.3KB)
   - Histórico de versões
   - Mudanças por sprint
   - Breaking changes
   - Roadmap futuro

---

## 🗺️ Guia de Leitura por Persona

### 👤 **Usuário Novo**

**Objetivo:** Rodar o cluster pela primeira vez

1. Ler [README.md](../README.md) - Seção "Quick Start"
2. Ler [MANUAL.md](MANUAL.md) - Seções 1-3 (Visão Geral, Instalação, Configuração)
3. Rodar o cluster local:
   ```bash
   bash test-cluster.sh
   python test-e2e.py
   ```
4. Se problemas, consultar [MANUAL.md](MANUAL.md) - Seção 7 (Troubleshooting)

**Tempo estimado:** 30 minutos

---

### 🛠️ **Desenvolvedor**

**Objetivo:** Contribuir com código

1. Ler [README.md](../README.md) - Entender o projeto
2. Ler [architecture.md](architecture.md) - Entender a arquitetura
3. Ler [CONTRIBUTING.md](../CONTRIBUTING.md) - Estilo de código e processo
4. Ler [TESTING.md](TESTING.md) - Como escrever e rodar testes
5. Setup ambiente de desenvolvimento:
   ```bash
   git clone https://github.com/hudsonrj/ch8-cluster-agent.git
   cd ch8-cluster-agent
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Ferramentas de dev
   pytest tests/  # Rodar testes
   ```
6. Criar branch e começar desenvolvimento

**Tempo estimado:** 1 hora

---

### 🚀 **DevOps / SRE**

**Objetivo:** Deploy em produção

1. Ler [README.md](../README.md) - Visão geral
2. Ler [DEPLOYMENT.md](DEPLOYMENT.md) - Seções 1-5 (todos os tipos de deployment)
3. Ler [DEPLOYMENT.md](DEPLOYMENT.md) - Seção 8 (Segurança)
4. Escolher estratégia de deployment:
   - **Single server:** Seção 1 (PM2/Systemd)
   - **Multi-máquina:** Seção 3 (topologia de rede)
   - **Containers:** Seção 5 (Docker Compose)
   - **Cloud:** Seção 4 (VPS) + Seção 6 (Kubernetes - Sprint 4)
5. Configurar monitoramento (Sprint 3)

**Tempo estimado:** 2-4 horas

---

### 🧑‍💼 **Product Manager / Stakeholder**

**Objetivo:** Entender capacidades e roadmap

1. Ler [README.md](../README.md) - Visão geral e features
2. Ler [MANUAL.md](MANUAL.md) - Seção 1 (Visão Geral) e Seção 8 (Casos de Uso)
3. Ler [CHANGELOG.md](../CHANGELOG.md) - O que foi feito e o que vem
4. Ler [decisions.md](decisions.md) - Por que certas decisões foram tomadas

**Tempo estimado:** 30 minutos

---

### 🔬 **Pesquisador / Estudante**

**Objetivo:** Entender a arquitetura de sistemas distribuídos

1. Ler [README.md](../README.md) - Overview
2. Ler [architecture.md](architecture.md) - Arquitetura detalhada
3. Ler [model-selection.md](model-selection.md) - Sistema de roteamento inteligente
4. Ler [decisions.md](decisions.md) - Trade-offs e alternativas
5. Ler [MANUAL.md](MANUAL.md) - Seções 5-6 (Arquitetura, API Reference)
6. Experimentar rodando localmente

**Tempo estimado:** 2 horas

---

## 📊 Estatísticas de Documentação

| Documento | Tamanho | Seções | Última Atualização |
|-----------|---------|--------|---------------------|
| README.md | 5.8KB | 10 | 2026-04-20 |
| MANUAL.md | 27KB | 10 | 2026-04-20 |
| DEPLOYMENT.md | 14KB | 8 | 2026-04-20 |
| TESTING.md | 18KB | 6 | 2026-04-20 |
| CONTRIBUTING.md | 9.4KB | 8 | 2026-04-20 |
| model-selection.md | 7.3KB | 5 | 2026-04-20 |
| CHANGELOG.md | 4.3KB | 3 | 2026-04-20 |
| **TOTAL** | **~86KB** | **50+** | Sprint 1 |

---

## 🔍 Como Buscar na Documentação

### Por Tópico

**Instalação:**
- [MANUAL.md](MANUAL.md) - Seção 2
- [DEPLOYMENT.md](DEPLOYMENT.md) - Seção 1

**Configuração:**
- [MANUAL.md](MANUAL.md) - Seção 3
- [model-selection.md](model-selection.md)

**Uso (submeter tarefas):**
- [MANUAL.md](MANUAL.md) - Seção 4
- [README.md](../README.md) - Quick Start

**Arquitetura:**
- [architecture.md](architecture.md)
- [MANUAL.md](MANUAL.md) - Seção 5

**API Reference:**
- [MANUAL.md](MANUAL.md) - Seção 6

**Troubleshooting:**
- [MANUAL.md](MANUAL.md) - Seção 7
- [TESTING.md](TESTING.md) - Seção 6

**Deployment:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Todas as seções

**Desenvolvimento:**
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [TESTING.md](TESTING.md)

---

## 📝 Notas

- Toda documentação está em **português brasileiro**
- Exemplos de código usam **Python 3.11+**
- Comandos assumem **Linux/macOS** (adaptações para Windows indicadas)
- Versão atual: **0.2.0-alpha** (Sprint 1 completo)

---

## 🔗 Links Externos

- **GitHub:** https://github.com/hudsonrj/ch8-cluster-agent
- **Issues:** https://github.com/hudsonrj/ch8-cluster-agent/issues
- **gRPC Docs:** https://grpc.io/docs/
- **Redis Docs:** https://redis.io/docs/
- **Ollama:** https://ollama.com/

---

## ✏️ Contribuir com Documentação

Documentação também aceita contribuições! Ver [CONTRIBUTING.md](../CONTRIBUTING.md) seção "Documentação".

**Diretrizes:**
- Manter português claro e objetivo
- Incluir exemplos práticos
- Testar comandos antes de documentar
- Usar emojis para clareza visual (moderadamente)
- Formatar com Markdown correto

**Ferramentas úteis:**
```bash
# Verificar links quebrados
npx markdown-link-check docs/*.md

# Lint markdown
npx markdownlint-cli docs/*.md

# Spell check (pt-BR)
aspell check -l pt_BR docs/MANUAL.md
```

---

**Mantido por:** Hudson RJ + PhiloSophia 🦉  
**Última atualização:** 2026-04-20 (Sprint 1 Complete)
