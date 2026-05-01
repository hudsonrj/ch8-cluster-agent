"""
CH8 Cluster High Availability — Orquestrador Master/Standby

Garante continuidade do orquestrador mesmo com falha do nó principal.

Arquitetura:
  - Um nó é eleito MASTER (líder) via controle centralizado
  - Um ou mais nós são STANDBY (espera quente)
  - Standby recebe heartbeats do master a cada SYNC_INTERVAL segundos
  - Se master para de responder por FAILOVER_TIMEOUT segundos, standby assume
  - O novo master notifica todos os nós da troca

Estado compartilhado (sincronizado):
  - Fila de tarefas pendentes
  - Histórico recente de tarefas (últimas N)
  - Configuração do cluster
  - Lista de nós e suas capacidades (já vem do control server)

Eleição de líder:
  - Critério: nó com maior score de capacidade (modelo mais forte + RAM + uptime)
  - Desempate: menor node_id lexicográfico (determinístico)
  - O control server é o árbitro (endpoint /api/cluster/leader)
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from .auth import CONTROL_URL, get_access_token, get_network_id, get_node_id
from .cluster_orchestrator import get_catalog, rank_nodes

log = logging.getLogger("ch8.ha")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
HA_STATE_FILE  = CONFIG_DIR / "ha_state.json"
HA_CONFIG_FILE = CONFIG_DIR / "ha_config.json"

# Intervalo de heartbeat master→standby (segundos)
SYNC_INTERVAL = 10

# Tempo sem heartbeat para declarar master morto
FAILOVER_TIMEOUT = 30

# Máximo de standbys mantidos sincronizados
MAX_STANDBYS = 2


# ── Estado HA ────────────────────────────────────────────────────────────────

def load_ha_state() -> dict:
    try:
        return json.loads(HA_STATE_FILE.read_text())
    except Exception:
        return {
            "role": "unknown",       # master | standby | worker
            "master_id": None,
            "master_hostname": None,
            "standbys": [],
            "last_master_seen": 0,
            "elected_at": 0,
            "failovers": 0,
        }


def save_ha_state(state: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = int(time.time())
    HA_STATE_FILE.write_text(json.dumps(state, indent=2))


def get_my_role() -> str:
    return load_ha_state().get("role", "worker")


def is_master() -> bool:
    state = load_ha_state()
    return state.get("master_id") == get_node_id()


def is_standby() -> bool:
    state = load_ha_state()
    return get_node_id() in [s.get("node_id") for s in state.get("standbys", [])]


# ── Eleição de Líder ──────────────────────────────────────────────────────────

def elect_master(nodes: Optional[List[Dict]] = None) -> Dict:
    """
    Elege o master com base na capacidade dos nós.
    Retorna o nó eleito como master.
    """
    if not nodes:
        nodes = get_catalog()
    if not nodes:
        return {}

    ranked = rank_nodes(nodes)
    master = ranked[0]
    standbys = ranked[1:MAX_STANDBYS + 1]

    log.info(f"Elected master: {master.get('hostname')} ({master.get('node_id','?')[:12]})")
    for s in standbys:
        log.info(f"  Standby: {s.get('hostname')} ({s.get('node_id','?')[:12]})")

    return {
        "master": master,
        "standbys": standbys,
        "elected_at": int(time.time()),
    }


def publish_election(master: Dict, standbys: List[Dict]) -> bool:
    """
    Publica a eleição no control server.
    Todos os nós consultam isso para saber quem é o master.
    """
    token = get_access_token()
    nid   = get_network_id()
    if not token:
        return False
    try:
        payload = {
            "network_id": nid,
            "master_id":       master.get("node_id"),
            "master_hostname": master.get("hostname"),
            "standbys": [
                {"node_id": s.get("node_id"), "hostname": s.get("hostname")}
                for s in standbys
            ],
            "elected_at": int(time.time()),
        }
        r = httpx.put(
            f"{CONTROL_URL}/api/cluster/leader",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        log.warning(f"Failed to publish election: {e}")
        return False


def get_current_leader() -> Optional[Dict]:
    """
    Busca o líder atual do control server.
    Retorna {"master_id", "master_hostname", "standbys", "elected_at"} ou None.
    """
    token = get_access_token()
    nid   = get_network_id()
    if not token:
        return None
    try:
        r = httpx.get(
            f"{CONTROL_URL}/api/cluster/leader",
            params={"network_id": nid},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.debug(f"get_current_leader: {e}")
    return None


# ── Sincronização Master → Standby ────────────────────────────────────────────

class MasterSyncState:
    """Estado que o master mantém e replica para os standbys."""

    def __init__(self):
        self.task_queue: List[Dict] = []    # tarefas pendentes
        self.task_history: List[Dict] = []  # últimas 50 tarefas concluídas
        self.cluster_config: Dict = {}      # configuração do cluster
        self.seq: int = 0                   # número de sequência (detecta gaps)

    def to_dict(self) -> dict:
        return {
            "seq":            self.seq,
            "ts":             int(time.time()),
            "task_queue":     self.task_queue[-20:],    # máx 20 pendentes
            "task_history":   self.task_history[-50:],  # máx 50 histórico
            "cluster_config": self.cluster_config,
        }

    def from_dict(self, d: dict):
        self.seq            = d.get("seq", 0)
        self.task_queue     = d.get("task_queue", [])
        self.task_history   = d.get("task_history", [])
        self.cluster_config = d.get("cluster_config", {})


# Instância global do estado HA
_sync_state = MasterSyncState()


async def _push_state_to_standby(standby: Dict, state_dict: dict) -> bool:
    """Envia estado atual para um standby via relay ou direto."""
    token = get_access_token()
    if not token:
        return False

    payload = {"ha_sync": state_dict, "stream": False}
    headers = {"Authorization": f"Bearer {token}"}
    node_id = standby.get("node_id", "")
    address = standby.get("address", "")
    orch_port = int(os.environ.get("CH8_AGENT_PORT", "7879"))

    # Direto
    if address:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(f"http://{address}:{orch_port}/ha/sync",
                                 json=payload, headers=headers)
                if r.status_code == 200:
                    return True
        except Exception:
            pass

    # Relay
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{CONTROL_URL}/api/relay/{node_id}/ha/sync",
                             json=payload, headers=headers)
            return r.status_code == 200
    except Exception as e:
        log.debug(f"push_state_to_standby {standby.get('hostname')}: {e}")
        return False


# ── Loop do Master ────────────────────────────────────────────────────────────

class MasterHA:
    """
    Roda no nó master.
    Envia heartbeat + estado para os standbys periodicamente.
    """

    def __init__(self, standbys: List[Dict]):
        self.standbys   = standbys
        self._stop      = asyncio.Event()

    async def run(self):
        log.info(f"Master HA started. Syncing to {len(self.standbys)} standby(s)")
        while not self._stop.is_set():
            await self._sync_tick()
            await asyncio.sleep(SYNC_INTERVAL)

    async def _sync_tick(self):
        _sync_state.seq += 1
        state = _sync_state.to_dict()
        state["master_id"]       = get_node_id()
        state["master_hostname"] = os.uname().nodename if hasattr(os, "uname") else "?"

        for standby in self.standbys:
            ok = await _push_state_to_standby(standby, state)
            if ok:
                log.debug(f"HA sync → {standby.get('hostname')} seq={_sync_state.seq}")
            else:
                log.warning(f"HA sync failed → {standby.get('hostname')}")

    def stop(self):
        self._stop.set()

    def update_standbys(self, standbys: List[Dict]):
        self.standbys = standbys


# ── Loop do Standby ───────────────────────────────────────────────────────────

class StandbyHA:
    """
    Roda no nó standby.
    Recebe estado do master e monitora se ele está vivo.
    Em caso de timeout, inicia eleição de failover.
    """

    def __init__(self, master: Dict):
        self.master            = master
        self._stop             = asyncio.Event()
        self._last_master_sync = time.time()
        self._failed_over      = False

    def on_sync_received(self, state_dict: dict):
        """Chamado quando recebe um sync do master."""
        _sync_state.from_dict(state_dict)
        self._last_master_sync = time.time()
        log.debug(f"HA sync received from master, seq={_sync_state.seq}")

        # Persiste estado localmente (para sobreviver a restart)
        state = load_ha_state()
        state["last_master_seen"] = int(time.time())
        state["master_seq"] = _sync_state.seq
        save_ha_state(state)

    async def run(self):
        log.info(f"Standby HA started. Watching master: {self.master.get('hostname')}")
        while not self._stop.is_set():
            await asyncio.sleep(5)
            # Use the file-based timestamp so the orchestrator's /ha/sync endpoint
            # (running in a different process) can reset the countdown
            file_last_seen = load_ha_state().get("last_master_seen", 0)
            effective_last = max(self._last_master_sync, float(file_last_seen))
            elapsed = time.time() - effective_last
            if elapsed > FAILOVER_TIMEOUT and not self._failed_over:
                log.warning(
                    f"Master {self.master.get('hostname')} silent for {elapsed:.0f}s — "
                    f"initiating failover!"
                )
                await self._do_failover()

    async def _do_failover(self):
        self._failed_over = True
        log.info("FAILOVER: taking over as master")

        # Registra no control server
        nodes = get_catalog()
        election = elect_master(nodes)
        new_master = election.get("master", {})

        if new_master.get("node_id") == get_node_id():
            # Sou o novo master
            log.info("FAILOVER: I am the new master")
            standbys = election.get("standbys", [])
            publish_election(new_master, standbys)

            state = load_ha_state()
            state["role"]             = "master"
            state["master_id"]        = get_node_id()
            state["master_hostname"]  = new_master.get("hostname")
            state["standbys"]         = standbys
            state["elected_at"]       = int(time.time())
            state["failovers"]        = state.get("failovers", 0) + 1
            save_ha_state(state)

            # Notifica todos os nós via relay
            token = get_access_token()
            if token:
                for node in nodes:
                    if node.get("node_id") == get_node_id():
                        continue
                    await _notify_new_master(node, new_master, standbys)
        else:
            log.info(f"FAILOVER: {new_master.get('hostname')} elected as new master")

        self._stop.set()

    def stop(self):
        self._stop.set()


async def _notify_new_master(node: Dict, master: Dict, standbys: List[Dict]):
    """Notifica um nó sobre o novo master."""
    token = get_access_token()
    payload = {
        "ha_new_master": {
            "master_id":       master.get("node_id"),
            "master_hostname": master.get("hostname"),
            "standbys":        standbys,
            "elected_at":      int(time.time()),
        }
    }
    headers = {"Authorization": f"Bearer {token}"}
    node_id = node.get("node_id", "")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(
                f"{CONTROL_URL}/api/relay/{node_id}/ha/new_master",
                json=payload, headers=headers
            )
    except Exception:
        pass


# ── Bootstrap HA ─────────────────────────────────────────────────────────────

def bootstrap_ha() -> dict:
    """
    Determina o papel deste nó (master/standby/worker) e inicializa o HA.
    Chamado durante o startup do daemon.

    Returns:
        {"role": "master"|"standby"|"worker", "master": {...}, "standbys": [...]}
    """
    my_id = get_node_id()
    nodes = get_catalog()

    if not nodes:
        log.info("HA: no other nodes — acting as standalone master")
        state = load_ha_state()
        state["role"]       = "master"
        state["master_id"]  = my_id
        state["standbys"]   = []
        save_ha_state(state)
        return {"role": "master", "master": {}, "standbys": []}

    # Verifica se já há líder eleito no control server
    leader_info = get_current_leader()

    if leader_info and leader_info.get("master_id"):
        master_id = leader_info["master_id"]
        standbys  = leader_info.get("standbys", [])
        standby_ids = [s.get("node_id") for s in standbys]

        if master_id == my_id:
            role = "master"
        elif my_id in standby_ids:
            role = "standby"
        else:
            role = "worker"

        log.info(f"HA: existing election — master={leader_info.get('master_hostname')}, role={role}")

        # Verifica se master ainda está online
        master_node = next((n for n in nodes if n["node_id"] == master_id), None)
        if not master_node and role != "master":
            log.warning("HA: master not in catalog, re-electing...")
            return _run_election(my_id, nodes)
    else:
        # Nenhuma eleição existente — realiza primeira eleição
        log.info("HA: no leader found — running first election")
        return _run_election(my_id, nodes)

    state = load_ha_state()
    state["role"]             = role
    state["master_id"]        = master_id
    state["master_hostname"]  = leader_info.get("master_hostname")
    state["standbys"]         = standbys
    save_ha_state(state)

    # Encontra objeto completo do master
    master_node = next((n for n in nodes if n["node_id"] == master_id), {})
    return {"role": role, "master": master_node, "standbys": standbys}


def _run_election(my_id: str, nodes: List[Dict]) -> dict:
    """Realiza eleição e salva resultado."""
    election = elect_master(nodes)
    master   = election.get("master", {})
    standbys = election.get("standbys", [])

    standby_ids = [s.get("node_id") for s in standbys]
    if master.get("node_id") == my_id:
        role = "master"
    elif my_id in standby_ids:
        role = "standby"
    else:
        role = "worker"

    # Só o master publica (evita race condition)
    if role == "master":
        publish_election(master, standbys)
        log.info(f"HA: Published election — I am master")
    else:
        log.info(f"HA: Master is {master.get('hostname')}, I am {role}")

    state = load_ha_state()
    state["role"]             = role
    state["master_id"]        = master.get("node_id")
    state["master_hostname"]  = master.get("hostname")
    state["standbys"]         = standbys
    state["elected_at"]       = int(time.time())
    save_ha_state(state)

    return {"role": role, "master": master, "standbys": standbys}


# ── API: status HA ────────────────────────────────────────────────────────────

def ha_status() -> dict:
    """Retorna status HA atual deste nó."""
    state = load_ha_state()
    return {
        "role":             state.get("role", "unknown"),
        "master_id":        state.get("master_id"),
        "master_hostname":  state.get("master_hostname"),
        "standbys":         state.get("standbys", []),
        "last_master_seen": state.get("last_master_seen", 0),
        "elected_at":       state.get("elected_at", 0),
        "failovers":        state.get("failovers", 0),
        "sync_seq":         _sync_state.seq,
        "task_queue_len":   len(_sync_state.task_queue),
        "task_history_len": len(_sync_state.task_history),
    }
