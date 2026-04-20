# 🤝 Guia de Contribuição

Obrigado por considerar contribuir com o CH8 Agent! 🎉

Este documento fornece diretrizes para contribuir com o projeto.

---

## 📋 Índice

1. [Código de Conduta](#código-de-conduta)
2. [Como Contribuir](#como-contribuir)
3. [Reportar Bugs](#reportar-bugs)
4. [Sugerir Features](#sugerir-features)
5. [Pull Requests](#pull-requests)
6. [Estilo de Código](#estilo-de-código)
7. [Commits](#commits)
8. [Testes](#testes)

---

## Código de Conduta

Este projeto adere a um código de conduta. Ao participar, você concorda em manter um ambiente respeitoso e inclusivo.

**Comportamentos esperados:**
- ✅ Ser respeitoso com diferentes opiniões
- ✅ Aceitar críticas construtivas
- ✅ Focar no que é melhor para a comunidade
- ✅ Mostrar empatia com outros membros

**Comportamentos inaceitáveis:**
- ❌ Linguagem ou imagens sexualizadas
- ❌ Trolling, insultos ou ataques pessoais
- ❌ Assédio público ou privado
- ❌ Publicar informações privadas de terceiros

---

## Como Contribuir

### 1. Fork o Repositório

```bash
# Clicar em "Fork" no GitHub
# Depois clonar seu fork:
git clone https://github.com/SEU-USUARIO/ch8-cluster-agent.git
cd ch8-cluster-agent
```

### 2. Criar Branch

```bash
# Sempre criar branch a partir de 'main'
git checkout main
git pull origin main

# Criar branch descritiva
git checkout -b feature/minha-feature
# ou
git checkout -b fix/corrigir-bug
```

**Convenções de nomes de branches:**
- `feature/nome` - Novas features
- `fix/nome` - Correções de bugs
- `docs/nome` - Apenas documentação
- `refactor/nome` - Refatoração de código
- `test/nome` - Adicionar/melhorar testes

### 3. Fazer Mudanças

```bash
# Editar arquivos
# Adicionar ao staging
git add .

# Commit (ver seção Commits)
git commit -m "feat: adiciona suporte para X"
```

### 4. Push e Pull Request

```bash
# Push para seu fork
git push origin feature/minha-feature

# Abrir Pull Request no GitHub
# Descrever o que foi feito
# Referenciar issues relacionadas
```

---

## Reportar Bugs

Bugs são rastreados como [GitHub Issues](https://github.com/hudsonrj/ch8-cluster-agent/issues).

**Antes de reportar:**
- Verifique se o bug já foi reportado (buscar issues)
- Teste na versão mais recente (main branch)
- Colete informações do sistema

**Template de Bug Report:**

```markdown
**Descrição do Bug**
Uma descrição clara do que está errado.

**Passos para Reproduzir**
1. Iniciar cluster com '...'
2. Executar comando '...'
3. Ver erro

**Comportamento Esperado**
O que deveria acontecer.

**Comportamento Atual**
O que está acontecendo.

**Screenshots**
Se aplicável, adicionar screenshots.

**Ambiente:**
- OS: [e.g. Ubuntu 22.04]
- Python: [e.g. 3.11.2]
- CH8 Version: [e.g. 0.2.0]
- Redis Version: [e.g. 7.0]

**Logs**
```
Cole logs relevantes aqui
```

**Contexto Adicional**
Qualquer outra informação relevante.
```

---

## Sugerir Features

Features são bem-vindas! Abra uma [GitHub Issue](https://github.com/hudsonrj/ch8-cluster-agent/issues) com:

**Template de Feature Request:**

```markdown
**Problema que resolve**
Explique o problema ou limitação atual.

**Solução proposta**
Descreva como a feature resolveria o problema.

**Alternativas consideradas**
Outras formas de resolver (se aplicável).

**Impacto**
- Performance: [baixo/médio/alto]
- Complexidade: [baixa/média/alta]
- Breaking changes: [sim/não]

**Casos de uso**
Exemplos concretos de como seria usada.
```

---

## Pull Requests

### Checklist Antes de Submeter

- [ ] Código segue o [estilo](#estilo-de-código)
- [ ] Commits seguem o [padrão](#commits)
- [ ] Testes passam (`pytest tests/`)
- [ ] Cobertura não diminuiu (`pytest --cov`)
- [ ] Documentação atualizada (se aplicável)
- [ ] CHANGELOG.md atualizado
- [ ] PR tem descrição clara

### Processo de Review

1. **Automático:** CI/CD roda testes
2. **Revisão de código:** Mantenedor revisa
3. **Discussão:** Iteração se necessário
4. **Aprovação:** PR aprovado
5. **Merge:** Integrado ao main

**Tempo de resposta esperado:** 2-5 dias úteis

### PR Template

```markdown
## Descrição
Resumo das mudanças.

## Tipo de mudança
- [ ] Bug fix (não quebra funcionalidade existente)
- [ ] Nova feature (adiciona funcionalidade)
- [ ] Breaking change (mudança incompatível)
- [ ] Documentação

## Testes
- [ ] Testes unitários adicionados/atualizados
- [ ] Testes de integração adicionados
- [ ] Testes passam localmente

## Checklist
- [ ] Código segue estilo do projeto
- [ ] Self-review realizado
- [ ] Comentários em código complexo
- [ ] Documentação atualizada
- [ ] CHANGELOG.md atualizado
- [ ] Nenhum warning novo

## Issues relacionadas
Closes #123
Related to #456
```

---

## Estilo de Código

### Python (PEP 8 + Black)

**Formatter:**
```bash
# Instalar
pip install black isort

# Formatar
black cluster/ tests/
isort cluster/ tests/

# Verificar (não modificar)
black --check cluster/
```

**Linter:**
```bash
# Instalar
pip install flake8 pylint

# Rodar
flake8 cluster/ --max-line-length=88
pylint cluster/ --max-line-length=88
```

**Exemplos:**

✅ **BOM:**
```python
def process_task(task_id: str, payload: Dict[str, Any]) -> TaskResult:
    """
    Processa uma tarefa e retorna o resultado.
    
    Args:
        task_id: ID único da tarefa
        payload: Dados da tarefa
        
    Returns:
        Resultado da execução
        
    Raises:
        TaskError: Se tarefa falhar
    """
    logger.info(f"Processing task {task_id}")
    
    try:
        result = execute(payload)
        return TaskResult(success=True, output=result)
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise TaskError(f"Execution failed: {e}") from e
```

❌ **RUIM:**
```python
def process(t,p):  # Nomes ruins
    print("Processing...")  # Usar logger
    r = exec(p)  # Nome de variável ruim
    return r  # Sem tratamento de erro
```

### Convenções

**Nomes:**
- `snake_case` para funções e variáveis
- `PascalCase` para classes
- `UPPER_CASE` para constantes
- Nomes descritivos (não abreviar excessivamente)

**Docstrings:**
- Todas as funções públicas devem ter docstring
- Formato: Google Style Python Docstrings
- Incluir Args, Returns, Raises

**Type Hints:**
```python
# Sempre usar type hints
def greet(name: str, age: int) -> str:
    return f"Hello {name}, you are {age}"

# Usar Optional para valores opcionais
from typing import Optional
def find_user(user_id: str) -> Optional[User]:
    pass

# Usar Union para múltiplos tipos
from typing import Union
def process(data: Union[str, bytes]) -> bool:
    pass
```

**Imports:**
```python
# Ordem:
# 1. Standard library
import os
import sys
from typing import Dict, List

# 2. Third-party
import grpc
import redis

# 3. Local
from cluster.discovery import ServiceDiscovery
from protos import cluster_pb2
```

---

## Commits

### Conventional Commits

Seguimos [Conventional Commits](https://www.conventionalcommits.org/pt-br/).

**Formato:**
```
<tipo>(<escopo>): <descrição>

[corpo opcional]

[rodapé opcional]
```

**Tipos:**
- `feat:` Nova feature
- `fix:` Correção de bug
- `docs:` Apenas documentação
- `style:` Formatação (não muda lógica)
- `refactor:` Refatoração (não adiciona feature nem corrige bug)
- `perf:` Melhoria de performance
- `test:` Adicionar/corrigir testes
- `chore:` Manutenção (deps, config, etc)
- `ci:` Mudanças em CI/CD

**Exemplos:**

✅ **BOM:**
```
feat(worker): adiciona suporte para GPU

Implementa detecção automática de GPU e roteamento
de tarefas pesadas para workers com CUDA.

Closes #42
```

```
fix(master): corrige race condition em heartbeat

O método process_heartbeat não era thread-safe,
causando inconsistências no Redis.

Fixes #67
```

```
docs: atualiza DEPLOYMENT.md com seção Kubernetes
```

❌ **RUIM:**
```
Update stuff
```

```
Fixed bug
```

```
WIP
```

### Commits Atômicos

- **1 commit = 1 mudança lógica**
- Commits devem ser autossuficientes
- Se precisa "e", talvez sejam 2 commits

✅ **BOM:**
```
feat(worker): adiciona model_manager
feat(worker): integra model_manager com executor
test(worker): adiciona testes para model_manager
```

❌ **RUIM:**
```
feat: model manager, integration, tests and docs
```

---

## Testes

### Obrigatório

- **Cobertura mínima:** 80%
- **Todos os testes devem passar:** `pytest tests/`
- **Sem warnings:** `pytest tests/ -W error`

### Estrutura

```python
# tests/unit/test_feature.py
import pytest
from cluster.feature import MyFeature

@pytest.fixture
def feature():
    """Fixture reutilizável"""
    return MyFeature(config={...})

def test_basic_functionality(feature):
    """Testa funcionalidade básica"""
    result = feature.process("input")
    assert result == "expected"

def test_error_handling(feature):
    """Testa tratamento de erro"""
    with pytest.raises(ValueError):
        feature.process(None)

@pytest.mark.slow
def test_heavy_operation(feature):
    """Testes lentos marcados"""
    result = feature.expensive_operation()
    assert result is not None
```

### Rodar Testes

```bash
# Todos os testes
pytest tests/ -v

# Apenas rápidos (skip @pytest.mark.slow)
pytest tests/ -m "not slow"

# Com cobertura
pytest tests/ --cov=cluster --cov-report=html

# Específico
pytest tests/unit/test_discovery.py::test_register_worker -v
```

---

## Dúvidas?

- **GitHub Issues:** Perguntas são bem-vindas
- **Email:** hudson@example.com
- **Discord:** (em breve)

---

**Obrigado por contribuir! 🚀**

_Baseado em contribuição de projetos open source estabelecidos._
