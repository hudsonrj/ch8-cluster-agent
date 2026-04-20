# 📝 CHANGELOG

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não Lançado]

### Sprint 2 (Planejado - 2026-04-27)
- [ ] HTTP REST API no master (FastAPI)
- [ ] Integração completa task queue
- [ ] Execução de modelos via LiteLLM
- [ ] Task retry com backoff exponencial
- [ ] WebSocket para streaming de resultados
- [ ] TLS/SSL para gRPC
- [ ] Métricas básicas (Prometheus format)

### Sprint 3 (Planejado - 2026-05-11)
- [ ] MCP capability registry
- [ ] OpenRAG per-node (PostgreSQL + pgvector)
- [ ] Distributed search coordination
- [ ] Worker specialization system
- [ ] Cost tracking dashboard
- [ ] Grafana dashboards
- [ ] Centralized logging

### Sprint 4 (Planejado - 2026-05-25)
- [ ] Kubernetes deployment (Helm charts)
- [ ] Horizontal pod autoscaling
- [ ] GPU worker support
- [ ] Multi-region coordination
- [ ] Advanced monitoring
- [ ] Load testing suite

---

## [0.2.0] - 2026-04-20

### ✨ Adicionado
- **Redis service discovery** completo com TTL automático
- **Master gRPC server** funcional:
  - `RegisterWorker()` - Registro de workers
  - `ProcessHeartbeat()` - Processamento de heartbeats
  - Worker selection por menor carga
  - Fila de tasks
  - Armazenamento de resultados
- **Worker gRPC client** funcional:
  - Auto-registro no master ao iniciar
  - gRPC server para receber tasks
  - Heartbeats automáticos a cada 10s
  - Execução de tasks
  - Report de resultados ao master
- **Model selection system** completo:
  - Suporte para modelos locais (Ollama)
  - Suporte para APIs (OpenRouter, Groq)
  - Roteamento automático por tamanho/privacidade/complexidade
  - Configuração YAML flexível
- **Testing suite completo**:
  - `test-cluster.sh` - Inicia master + 2 workers
  - `test-e2e.py` - Valida status do cluster
  - `test-submit.py` - Envia tasks de teste
  - `stop-cluster.sh` - Para todos os processos
- **Documentação completa**:
  - `docs/MANUAL.md` - Manual completo (27KB, 10 seções)
  - `docs/TESTING.md` - Guia de testes (18KB)
  - `docs/DEPLOYMENT.md` - Guia de deployment (14KB)
  - `docs/architecture.md` - Visão geral da arquitetura
  - `docs/model-selection.md` - Sistema de seleção de modelos
  - `docs/decisions.md` - Decisões técnicas
  - README.md atualizado com Sprint 1 status

### 🔨 Modificado
- `cluster/master.py` expandido de 3.7KB para versão funcional
- `cluster/worker.py` expandido de 5.6KB para versão funcional
- `config/worker.yaml` com exemplos completos de configuração
- README.md atualizado com status Sprint 1 completo

### 🐛 Corrigido
- Nenhum (primeiro release funcional)

### 📊 Estatísticas Sprint 1
- **Duração:** 21 segundos (subagente)
- **Tokens processados:** 110.6k
- **Arquivos criados/modificados:** 10+
- **Linhas de código:** ~2.000+
- **Documentação:** 60KB+
- **Commits:** 4 (90764cd, e869444, b9e2859, 8ee9a66)

---

## [0.1.0] - 2026-04-20

### ✨ Adicionado
- Estrutura inicial do projeto
- gRPC protocol definitions (`protos/cluster.proto`)
- Compilação de protobuf → `cluster_pb2.py` + `cluster_pb2_grpc.py`
- Esqueleto `cluster/master.py` (3.7KB)
- Esqueleto `cluster/worker.py` (5.6KB)
- `config/worker.yaml` básico
- Git repository inicializado
- venv Python com dependências básicas

### 📝 Decisões Arquiteturais
- **Protocolo:** gRPC escolhido (vs WebSocket) para performance
- **Service Discovery:** Redis escolhido (vs etcd) por simplicidade
- **Modelos:** Suporte híbrido local (Ollama) + API (OpenRouter/Groq)
- **Prioridades:** Simplicidade > Performance > Resiliência
- **Hardware alvo:** Notebooks antigos (4GB), Raspberry Pi, VPS baratos

---

## Tipos de Mudanças

- `✨ Adicionado` - Novas features
- `🔨 Modificado` - Mudanças em features existentes
- `❌ Removido` - Features removidas
- `🐛 Corrigido` - Bug fixes
- `🔒 Segurança` - Vulnerabilidades corrigidas
- `📝 Documentação` - Apenas mudanças em docs
- `⚡ Performance` - Melhorias de performance

---

## Links

- [Repositório GitHub](https://github.com/hudsonrj/ch8-cluster-agent)
- [Issues](https://github.com/hudsonrj/ch8-cluster-agent/issues)
- [Documentação Completa](docs/MANUAL.md)

---

**Mantido por:** Hudson RJ ([@hudsonrj28](https://github.com/hudsonrj28)) + PhiloSophia 🦉  
**Licença:** MIT
