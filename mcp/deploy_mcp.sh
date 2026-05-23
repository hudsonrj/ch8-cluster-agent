#!/bin/bash
# deploy_mcp.sh — instala e inicia o CH8 MCP Server em todos os nodes online
# Uso: bash /data/ch8-agent/mcp/deploy_mcp.sh
set -e

MCP_PORT=${CH8_MCP_PORT:-8765}
AGENT_DIR="/data/ch8-agent"
MCP_SCRIPT="$AGENT_DIR/mcp/ch8_mcp_server.py"
TOKEN=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.config/ch8/auth.json')))['access_token'])" 2>/dev/null)

echo "[MCP Deploy] Iniciando deploy em todos os nodes..."

# ── 1. Instalar e iniciar no manager1 (local) ──────────────────────────────
echo "[manager1] Instalando dependências..."
pip install mcp fastmcp --quiet --ignore-installed rich 2>/dev/null || true

echo "[manager1] Iniciando MCP server na porta $MCP_PORT..."
pkill -f "ch8_mcp_server.py" 2>/dev/null || true
sleep 1
nohup python3 "$MCP_SCRIPT" \
    >> /root/.config/ch8/mcp_server.log 2>&1 &
echo "[manager1] MCP server pid=$!"
sleep 3
curl -s "http://127.0.0.1:$MCP_PORT/mcp" -o /dev/null -w "HTTP %{http_code}" && echo " — OK" || echo " — FAIL"

# ── 2. Deploy nos nodes remotos via /update + relay ────────────────────────
# Obter lista de nodes online
NODES=$(python3 -c "
import sys, json, os, httpx
sys.path.insert(0, '$AGENT_DIR')
from connect.auth import CONTROL_URL, get_network_id
token = '$TOKEN'
r = httpx.get(f'{CONTROL_URL}/nodes', params={'network_id': get_network_id()},
              headers={'Authorization': f'Bearer {token}'}, timeout=10)
nodes = r.json().get('nodes', [])
for n in nodes:
    if n.get('status') == 'online' and n.get('hostname') not in ('localhost','manager1'):
        print(n['hostname'], n['node_id'], n.get('address',''))
" 2>/dev/null)

echo ""
echo "[MCP Deploy] Nodes online para deploy:"
echo "$NODES"
echo ""

while IFS=' ' read -r hostname node_id address; do
    [ -z "$hostname" ] && continue
    echo "[${hostname}] Disparando git pull + start MCP..."

    # Trigger /update para puxar o código novo
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "http://${address}:7879/update" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"ref":"master"}' --max-time 10 2>/dev/null || echo "000")

    if [ "$STATUS" = "200" ]; then
        echo "[${hostname}] Update ok — aguardando restart..."
        sleep 5

        # Iniciar MCP via execute remoto
        EXEC_RESP=$(curl -s -X POST "http://${address}:7879/execute" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"name\":\"shell_exec\",\"args\":{\"command\":\"pip install mcp fastmcp --quiet --ignore-installed rich 2>/dev/null; pkill -f ch8_mcp_server.py 2>/dev/null; sleep 1; nohup python3 $MCP_SCRIPT >> ~/.config/ch8/mcp_server.log 2>&1 & echo started:\$!\",\"timeout\":60}}" \
            --max-time 90 2>/dev/null)
        echo "[${hostname}] $EXEC_RESP" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print(d.get('result',{}).get('stdout','?')[:80])
except: print(sys.stdin.read()[:80])
" 2>/dev/null || echo "[${hostname}] sem resposta"
    else
        echo "[${hostname}] Update falhou (HTTP $STATUS) — pulando"
    fi
done <<< "$NODES"

echo ""
echo "[MCP Deploy] Concluido!"
echo "  MCP URL local: http://127.0.0.1:$MCP_PORT/mcp"
echo "  Claude config: {\"type\":\"http\",\"url\":\"http://127.0.0.1:$MCP_PORT/mcp\"}"
