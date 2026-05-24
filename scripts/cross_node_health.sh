#!/bin/bash
# cross_node_health.sh — verifica saúde básica de todos os nodes via control server
TOKEN=$(python3 -c "import json,os; print(json.load(open(os.path.expanduser('~/.config/ch8/auth.json')))['access_token'])")
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8081/nodes?network_id=net_default | \
  python3 -c "
import sys,json,time
nodes=json.load(sys.stdin).get('nodes',[])
now=time.time()
print(f'Nodes: {len(nodes)} total')
for n in nodes:
    age=int(now-n.get('last_seen',0))
    disk=n.get('disk_pct',0)
    status=n.get('status')
    flag=' ⚠️' if disk>88 or status!='online' or age>300 else ''
    print(f'  {n["hostname"]:28} {status:8} disk={disk}% last={age}s{flag}')
"
