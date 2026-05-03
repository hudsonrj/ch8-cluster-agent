"""
CH8 Cluster Orchestrator

Orquestra tarefas distribuídas pelo cluster:

1. Mantém catálogo vivo de todos os nós (modelos, CPU, RAM, serviços)
2. Recebe uma tarefa, planeja com o modelo mais forte disponível
3. Quebra em subtarefas proporcionais à capacidade de cada nó
4. Executa em paralelo, monitora, cobra retry se necessário
5. Consolida tudo num resultado único

Fluxo:
  cluster_task(task)
    ├── get_catalog()          → todos os nós com capacidades
    ├── plan(task, catalog)    → plano JSON com subtarefas por nó
    ├── execute_parallel(plan) → envia para todos os nós ao mesmo tempo
    └── consolidate(results)   → junta tudo num output coeso
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .auth import CONTROL_URL, get_access_token, get_network_id, get_node_id
from .ai_config import get_ai_client, get_provider_info

log = logging.getLogger("ch8.cluster")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))


def _run_async(coro):
    """Run an async coroutine from sync code, handling nested event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context (e.g. called from FastAPI handler)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)

# Timeout para esperar resposta de cada nó (segundos)
NODE_TIMEOUT = 30

# Máximo de tentativas por subtarefa
MAX_RETRIES = 1


# ── Catálogo ────────────────────────────────────────────────────────────────

def get_catalog() -> List[Dict]:
    """
    Retorna todos os nós online do cluster com suas capacidades completas.
    Inclui: modelos, CPU, RAM, serviços, ferramentas, provedor AI.
    """
    token = get_access_token()
    nid   = get_network_id()
    if not token or not nid:
        return []
    try:
        r = httpx.get(
            f"{CONTROL_URL}/nodes",
            params={"network_id": nid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            nodes = r.json().get("nodes", [])
            # Filtra nós online com AI configurado
            return [n for n in nodes if n.get("status") == "online"]
    except Exception as e:
        log.warning(f"Failed to fetch catalog: {e}")
    return []


def catalog_summary(nodes: List[Dict]) -> str:
    """
    Gera uma descrição textual do catálogo para o planner LLM entender.
    """
    if not nodes:
        return "Nenhum nó disponível no cluster."

    my_id = get_node_id()
    lines = [f"Cluster com {len(nodes)} nó(s) online:\n"]

    for n in nodes:
        nid      = n.get("node_id", "?")
        name     = n.get("hostname", nid[:12])
        is_me    = " [ESTE NÓ]" if nid == my_id else ""
        provider = n.get("ai_provider", "?")
        model    = n.get("ai_model", "?")
        cpu_c    = n.get("cpu_cores", "?")
        mem_gb   = n.get("mem_total_gb", 0)
        mem_pct  = n.get("mem_pct", 0)
        cpu_pct  = n.get("cpu_pct", 0)
        caps     = n.get("capabilities", [])
        models   = n.get("models", [])          # modelos ollama locais
        services = [s.get("name","?") for s in n.get("services", [])[:6]]
        tools    = n.get("tools", [])

        ollama_str   = f"  Ollama: {', '.join(models)}\n" if models else ""
        services_str = f"  Serviços: {', '.join(services)}\n" if services else ""
        tools_str    = f"  Ferramentas: {', '.join(tools)}\n" if tools else ""

        lines.append(
            f"- {name}{is_me} (id={nid})\n"
            f"  AI: {provider} / {model}\n"
            f"  Hardware: {cpu_c} cores, {mem_gb:.1f}GB RAM "
            f"(uso: CPU {cpu_pct}%, RAM {mem_pct}%)\n"
            f"  Capacidades: {', '.join(caps)}\n"
            f"{ollama_str}{services_str}{tools_str}"
        )
    return "\n".join(lines)


def rank_nodes(nodes: List[Dict]) -> List[Dict]:
    """
    Ordena nós por poder de processamento (mais forte primeiro).
    Critérios: modelo forte > RAM > CPU cores.
    """
    MODEL_RANK = {
        "claude-opus": 100, "claude-sonnet": 90, "claude-haiku": 70,
        "gpt-4o": 95, "gpt-4": 85, "gpt-3.5": 60,
        "gemini-pro": 80, "gemini-flash": 65,
        "llama3.3": 70, "llama3.2": 60, "llama3.1": 55, "llama3": 50,
        "qwen2.5": 55, "qwen2": 45,
        "mistral": 50, "mixtral": 65,
        "deepseek": 60, "phi4": 55, "phi3": 45,
    }

    # Load manual priorities from ~/.config/ch8/ha_priority.json
    # Format: {"node_id": bonus_score}  e.g. {"node_23b8a646e03f3e74": 99999}
    import json as _json
    _prio_file = CONFIG_DIR / "ha_priority.json"
    _priorities: dict = {}
    try:
        _priorities = _json.loads(_prio_file.read_text())
    except Exception:
        pass

    def score(n):
        model = n.get("ai_model", "").lower()
        rank  = max((v for k, v in MODEL_RANK.items() if k in model), default=30)
        # local ollama models add bonus if capable
        if n.get("models"):
            best_local = max(
                (v for m in n["models"] for k, v in MODEL_RANK.items() if k in m.lower()),
                default=0
            )
            rank = max(rank, best_local)
        mem   = n.get("mem_total_gb", 0)
        cores = n.get("cpu_cores", 1)
        load  = n.get("cpu_pct", 0) + n.get("mem_pct", 0)
        prio  = _priorities.get(n.get("node_id", ""), 0)
        return rank * 100 + mem * 10 + cores * 2 - load + prio

    return sorted(nodes, key=score, reverse=True)


# ── Planejamento ─────────────────────────────────────────────────────────────

PLAN_PROMPT = """\
Você é o planejador de um cluster de agentes de IA distribuídos.

TAREFA DO USUÁRIO:
{task}

CATÁLOGO DO CLUSTER (nós disponíveis):
{catalog}

INSTRUÇÕES:
1. Analise a tarefa e decida se ela pode ser paralelizada ou deve ser feita em sequência.
2. Para cada parte da tarefa, escolha o nó mais adequado (considere RAM, modelo, serviços disponíveis).
3. Crie subtarefas claras e independentes quando possível.
4. Subtarefas complexas devem ir para nós com modelos mais fortes.
5. Subtarefas simples (extração de dados, queries, scripts) podem ir para nós menores.
6. Nunca crie mais subtarefas do que o necessário.

Responda SOMENTE com um JSON no formato abaixo, sem texto adicional:
{{
  "strategy": "parallel" | "sequential",
  "reasoning": "Breve explicação do plano (1-2 linhas)",
  "subtasks": [
    {{
      "id": "s1",
      "node_id": "<node_id exato do catálogo>",
      "node_name": "<hostname>",
      "instruction": "<instrução completa e auto-contida para este nó>",
      "context": "<contexto relevante se necessário>",
      "priority": 1,
      "complexity": "high" | "medium" | "low"
    }}
  ]
}}

IMPORTANTE:
- Use apenas node_ids que aparecem no catálogo acima.
- Cada subtarefa deve ser completa — o nó não tem contexto extra além do que você escrever.
- Se a tarefa é simples e pode ser feita por um único nó, crie apenas 1 subtarefa.
"""

CONSOLIDATE_PROMPT = """\
Você é o consolidador final de uma tarefa distribuída em cluster.

TAREFA ORIGINAL:
{task}

PLANO USADO:
{plan_reasoning}

RESULTADOS DOS NÓS:
{results}

INSTRUÇÕES:
Consolide todos os resultados parciais em uma resposta ÚNICA, coesa e completa.
- Elimine duplicatas e contradições.
- Organize a informação de forma lógica.
- Se houve erros em alguns nós, mencione isso de forma resumida e use os resultados válidos.
- A resposta final deve ser como se um único agente muito capaz tivesse feito tudo.
"""


def plan_task(task: str, catalog: List[Dict], ai_client=None) -> Dict:
    """
    Usa o modelo local para criar um plano de execução distribuída.
    Retorna o plano como dict.
    """
    if not catalog:
        # Sem cluster, executa localmente
        my_id = get_node_id()
        return {
            "strategy": "sequential",
            "reasoning": "Nenhum nó no cluster, executando localmente.",
            "subtasks": [{
                "id": "s1", "node_id": my_id, "node_name": "local",
                "instruction": task, "context": "", "priority": 1, "complexity": "high"
            }]
        }

    ranked = rank_nodes(catalog)
    summary = catalog_summary(ranked)
    prompt  = PLAN_PROMPT.format(task=task, catalog=summary)

    try:
        if ai_client is None:
            ai_client = get_ai_client()

        log.info("Planning task with AI...")
        response = ai_client.chat([{"role": "user", "content": prompt}],
                                   max_tokens=2000, temperature=0.1)

        # Extrair JSON da resposta
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        plan = json.loads(text)
        log.info(f"Plan: {plan.get('strategy')} with {len(plan.get('subtasks',[]))} subtasks")
        return plan

    except Exception as e:
        log.error(f"Planning failed: {e} — falling back to single-node")
        best_node = ranked[0] if ranked else None
        return {
            "strategy": "sequential",
            "reasoning": f"Planejamento automático falhou ({e}), usando nó mais forte.",
            "subtasks": [{
                "id": "s1",
                "node_id": best_node["node_id"] if best_node else get_node_id(),
                "node_name": best_node.get("hostname", "best") if best_node else "local",
                "instruction": task, "context": "", "priority": 1, "complexity": "high"
            }]
        }


# ── Execução distribuída ─────────────────────────────────────────────────────

async def _collect_chat_response(url: str, payload: dict, headers: dict) -> Optional[str]:
    """
    Send a chat request and collect the full response.
    Handles both JSON responses and SSE streaming.
    Returns the collected text or None on failure.
    """
    async with httpx.AsyncClient(timeout=NODE_TIMEOUT) as c:
        r = await c.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

        content_type = r.headers.get("content-type", "")

        # SSE streaming response
        if "text/event-stream" in content_type or r.text.startswith("data:"):
            collected = []
            for line in r.text.split("\n"):
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    msg = json.loads(data_str)
                    content = msg.get("message", {}).get("content", "")
                    if content:
                        collected.append(content)
                    elif msg.get("response"):
                        collected.append(msg["response"])
                    elif msg.get("error"):
                        raise RuntimeError(msg["error"])
                except json.JSONDecodeError:
                    pass
            text = "".join(collected)
            return text if text else None

        # Regular JSON response
        try:
            data = r.json()
            return data.get("response") or data.get("result") or data.get("message", {}).get("content", "")
        except Exception:
            return r.text[:2000] if r.text else None


async def _send_to_node_async(
    subtask: Dict,
    catalog: List[Dict],
    retries: int = MAX_RETRIES,
) -> Dict:
    """
    Envia uma subtarefa para um nó via conexão direta ou relay.
    Retorna {"subtask_id", "node_name", "result" | "error", "method", "elapsed"}.
    """
    subtask_id = subtask["id"]
    node_id    = subtask["node_id"]
    node_name  = subtask.get("node_name", node_id[:12])
    instruction = subtask["instruction"]
    context     = subtask.get("context", "")

    message = instruction
    if context:
        message = f"{instruction}\n\nContexto: {context}"

    # Encontra endereço do nó no catálogo
    node_info = next((n for n in catalog if n["node_id"] == node_id), None)
    my_id = get_node_id()

    t0 = time.time()
    last_error = None

    for attempt in range(retries + 1):
        if attempt > 0:
            log.info(f"[{node_name}] Retry {attempt}/{retries} for subtask {subtask_id}")
            await asyncio.sleep(3 * attempt)

        # Execução local (este nó)
        if node_id == my_id:
            try:
                result = await _run_locally(message)
                elapsed = time.time() - t0
                log.info(f"[{node_name}] Local execution OK ({elapsed:.1f}s)")
                return {"subtask_id": subtask_id, "node_name": node_name,
                        "result": result, "method": "local", "elapsed": elapsed}
            except Exception as e:
                last_error = str(e)
                log.warning(f"[{node_name}] Local execution failed: {e}")
                continue

        # Execução remota
        payload = {"message": message}
        token = get_access_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))

        # Tenta direto primeiro
        if node_info and node_info.get("address"):
            addr = node_info["address"]
            url  = f"http://{addr}:{orch_port}/chat"
            try:
                result_text = await _collect_chat_response(url, payload, headers)
                if result_text is not None:
                    elapsed = time.time() - t0
                    log.info(f"[{node_name}] Direct OK ({elapsed:.1f}s)")
                    return {"subtask_id": subtask_id, "node_name": node_name,
                            "result": result_text, "method": "direct", "elapsed": elapsed}
                last_error = "Direct: empty response"
            except Exception as e:
                last_error = str(e)

        # Fallback para relay
        if token:
            relay_url = f"{CONTROL_URL}/api/relay/{node_id}"
            try:
                result_text = await _collect_chat_response(relay_url, payload, headers)
                if result_text is not None:
                    elapsed = time.time() - t0
                    log.info(f"[{node_name}] Relay OK ({elapsed:.1f}s)")
                    return {"subtask_id": subtask_id, "node_name": node_name,
                            "result": result_text, "method": "relay", "elapsed": elapsed}
                last_error = "Relay: empty response"
            except Exception as e:
                last_error = f"Relay: {e}"

        log.warning(f"[{node_name}] Attempt {attempt+1} failed: {last_error}")

    elapsed = time.time() - t0
    log.error(f"[{node_name}] All {retries+1} attempts failed for subtask {subtask_id}")
    return {"subtask_id": subtask_id, "node_name": node_name,
            "error": last_error, "method": "failed", "elapsed": elapsed}


async def _run_locally(message: str) -> str:
    """Executa uma tarefa localmente usando o AI client configurado."""
    ai_client = get_ai_client()
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: ai_client.chat([{"role": "user", "content": message}], max_tokens=4000)
    )
    return response


async def execute_plan_async(plan: Dict, catalog: List[Dict]) -> List[Dict]:
    """
    Executa o plano de subtarefas.
    - "parallel": todas ao mesmo tempo
    - "sequential": uma de cada vez, na ordem de prioridade
    """
    subtasks = sorted(plan.get("subtasks", []), key=lambda s: s.get("priority", 1))
    strategy = plan.get("strategy", "parallel")

    if not subtasks:
        return []

    log.info(f"Executing {len(subtasks)} subtasks ({strategy})")

    if strategy == "parallel":
        tasks = [_send_to_node_async(s, catalog) for s in subtasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                out.append({"subtask_id": subtasks[i]["id"],
                            "node_name": subtasks[i].get("node_name", "?"),
                            "error": str(r), "method": "failed", "elapsed": 0})
            else:
                out.append(r)
        return out
    else:
        # Sequential — cada resultado pode ser passado como contexto para o próximo
        results = []
        prior_context = ""
        for s in subtasks:
            if prior_context:
                s = dict(s)
                s["context"] = (s.get("context", "") + "\n\nResultado anterior:\n" + prior_context).strip()
            r = await _send_to_node_async(s, catalog)
            results.append(r)
            if "result" in r:
                prior_context = r["result"][:2000]
        return results


# ── Consolidação ──────────────────────────────────────────────────────────────

def consolidate_results(task: str, plan: Dict, results: List[Dict], ai_client=None) -> str:
    """
    Usa o modelo local para consolidar todos os resultados numa resposta única.
    """
    if not results:
        return "Nenhum resultado retornado pelo cluster."

    # Se só 1 subtarefa e foi bem-sucedida, retorna direto
    successful = [r for r in results if "result" in r]
    failed     = [r for r in results if "error" in r]

    if len(successful) == 1 and not failed:
        return successful[0]["result"]

    # Formata resultados para o LLM
    results_text = ""
    for r in results:
        node = r.get("node_name", "?")
        elapsed = r.get("elapsed", 0)
        method  = r.get("method", "?")
        if "result" in r:
            results_text += f"\n### Nó: {node} ({method}, {elapsed:.1f}s)\n{r['result']}\n"
        else:
            results_text += f"\n### Nó: {node} — ERRO: {r.get('error','?')}\n"

    if failed:
        fail_summary = f"\n⚠️ {len(failed)}/{len(results)} nó(s) falharam: {[f['node_name'] for f in failed]}"
        results_text += fail_summary

    if not successful:
        return f"Todos os nós falharam.\n{results_text}"

    prompt = CONSOLIDATE_PROMPT.format(
        task=task,
        plan_reasoning=plan.get("reasoning", ""),
        results=results_text
    )

    try:
        if ai_client is None:
            ai_client = get_ai_client()
        log.info("Consolidating results with AI...")
        return ai_client.chat([{"role": "user", "content": prompt}], max_tokens=8000)
    except Exception as e:
        log.error(f"Consolidation failed: {e} — returning raw results")
        return results_text


# ── Ponto de entrada principal ───────────────────────────────────────────────

def run_cluster_task(
    task: str,
    strategy: str = "auto",
    target_nodes: Optional[List[str]] = None,
    progress_cb=None,
) -> Dict:
    """
    Executa uma tarefa no cluster completo.

    Args:
        task:          Descrição da tarefa
        strategy:      "auto" (LLM decide), "parallel", "sequential", "broadcast"
        target_nodes:  Lista de hostnames/node_ids para restringir (None = todos)
        progress_cb:   Callback(step, message) para progresso em tempo real

    Returns:
        {
          "result": str,        # Resposta consolidada final
          "plan": dict,         # Plano usado
          "results": list,      # Resultados individuais por nó
          "nodes_used": int,
          "nodes_failed": int,
          "elapsed": float,
        }
    """
    t0 = time.time()

    def _progress(step, msg):
        log.info(f"[cluster] {step}: {msg}")
        if progress_cb:
            progress_cb(step, msg)

    # 1. Catálogo
    _progress("catalog", "Buscando nós do cluster...")
    catalog = get_catalog()

    if target_nodes:
        catalog = [n for n in catalog
                   if n.get("node_id") in target_nodes
                   or n.get("hostname") in target_nodes]

    _progress("catalog", f"{len(catalog)} nó(s) disponível(is)")

    # 2. Planejamento
    _progress("plan", "Planejando distribuição da tarefa...")
    ai = get_ai_client()

    # Override strategy se especificado
    if strategy == "broadcast":
        # Envia a mesma tarefa para todos os nós e consolida
        my_id = get_node_id()
        plan = {
            "strategy": "parallel",
            "reasoning": "Broadcast: mesma tarefa para todos os nós",
            "subtasks": [
                {"id": f"s{i+1}", "node_id": n["node_id"],
                 "node_name": n.get("hostname", n["node_id"][:12]),
                 "instruction": task, "context": "", "priority": 1, "complexity": "medium"}
                for i, n in enumerate(catalog)
            ]
        }
    else:
        plan = plan_task(task, catalog, ai_client=ai)
        if strategy in ("parallel", "sequential"):
            plan["strategy"] = strategy

    nodes_in_plan = {s["node_id"] for s in plan.get("subtasks", [])}
    _progress("plan",
              f"{plan['strategy'].upper()}: {len(plan['subtasks'])} subtarefa(s) "
              f"em {len(nodes_in_plan)} nó(s) — {plan.get('reasoning','')}")

    # 3. Execução
    _progress("execute", "Distribuindo e executando subtarefas...")
    results = _run_async(execute_plan_async(plan, catalog))

    successful = [r for r in results if "result" in r]
    failed     = [r for r in results if "error" in r]
    _progress("execute",
              f"{len(successful)} OK, {len(failed)} falhas | "
              f"máx={max((r.get('elapsed',0) for r in results), default=0):.1f}s")

    # 4. Consolidação
    _progress("consolidate", "Consolidando respostas...")
    final = consolidate_results(task, plan, results, ai_client=ai)

    elapsed = time.time() - t0
    _progress("done", f"Concluído em {elapsed:.1f}s")

    return {
        "result":       final,
        "plan":         plan,
        "results":      results,
        "nodes_used":   len(successful),
        "nodes_failed": len(failed),
        "elapsed":      elapsed,
    }


# ── Cluster Update ────────────────────────────────────────────────────────────

async def _get_node_version_async(node: Dict) -> Dict:
    """Fetch version/commit from a node."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))
    address = node.get("address", "")
    node_id = node.get("node_id", "")

    if address:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"http://{address}:{orch_port}/version", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    data["node_id"] = node_id
                    data["hostname"] = node.get("hostname", "")
                    return data
        except Exception:
            pass

    # Via relay
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{CONTROL_URL}/api/relay/{node_id}/version", headers=headers)
            if r.status_code == 200:
                data = r.json()
                data["node_id"] = node_id
                data["hostname"] = node.get("hostname", "")
                return data
    except Exception:
        pass

    return {"node_id": node_id, "hostname": node.get("hostname", ""), "error": "unreachable"}


async def _push_update_to_node_async(node: Dict, ref: str, repo: str) -> Dict:
    """Push update command to a single node."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))
    address = node.get("address", "")
    node_id = node.get("node_id", "")
    payload = {"ref": ref, "repo": repo}

    if address:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(f"http://{address}:{orch_port}/update",
                                 json=payload, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    data["node_id"] = node_id
                    data["hostname"] = node.get("hostname", "")
                    return data
        except Exception:
            pass

    # Via relay
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{CONTROL_URL}/api/relay/{node_id}/update",
                             json=payload, headers=headers)
            if r.status_code == 200:
                data = r.json()
                data["node_id"] = node_id
                data["hostname"] = node.get("hostname", "")
                return data
    except Exception as e:
        pass

    return {"node_id": node_id, "hostname": node.get("hostname", ""), "ok": False, "error": "unreachable"}


def update_cluster(ref: str = "main", repo: str = "", target_nodes: Optional[List[str]] = None,
                   progress_cb=None) -> Dict:
    """
    Master broadcasts a self-update to all cluster nodes.
    Each node will git pull origin/<ref> and restart its daemon.

    Args:
        ref:          Git branch or tag to update to (default: "main")
        repo:         Optional git remote URL override
        target_nodes: List of node_ids to update (default: all online nodes)
        progress_cb:  Optional callback(step, msg)

    Returns:
        {"updated": [...], "failed": [...], "skipped": [...], "elapsed": N}
    """
    def _progress(step, msg):
        log.info(f"[update/{step}] {msg}")
        if progress_cb:
            progress_cb(step, msg)

    t0 = time.time()
    catalog = get_catalog()
    if not catalog:
        return {"updated": [], "failed": [], "skipped": [], "elapsed": 0,
                "error": "No nodes in catalog"}

    my_id = get_node_id()

    # Filter to target nodes (exclude self — master updates itself separately)
    nodes = [n for n in catalog if n["node_id"] != my_id]
    if target_nodes:
        nodes = [n for n in nodes if n["node_id"] in target_nodes]

    _progress("start", f"Updating {len(nodes)} node(s) to ref={ref}")

    # Check current versions
    versions = _run_async(
        asyncio.gather(*[_get_node_version_async(n) for n in nodes])
    )
    for v in versions:
        _progress("version", f"{v.get('hostname','?')}: commit={v.get('commit','?')} version={v.get('version','?')}")

    # Push update to all nodes in parallel
    results = _run_async(
        asyncio.gather(*[_push_update_to_node_async(n, ref, repo) for n in nodes])
    )

    updated = [r for r in results if r.get("ok")]
    failed  = [r for r in results if not r.get("ok")]

    _progress("done", f"{len(updated)} updated, {len(failed)} failed in {time.time()-t0:.1f}s")

    return {
        "updated": updated,
        "failed":  failed,
        "skipped": [],
        "ref":     ref,
        "elapsed": round(time.time() - t0, 1),
    }
