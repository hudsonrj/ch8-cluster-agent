#!/bin/bash
# Quick test script - Start all components in background for testing

set -e

cd /data/ch8-agent-cluster

echo "======================================"
echo "  CH8 Agent Cluster - Quick Test"
echo "======================================"
echo ""

# Activate venv
source venv/bin/activate

# Check Redis
echo "Checking Redis..."
redis-cli ping > /dev/null 2>&1 && echo "✅ Redis is running" || (echo "❌ Redis not running! Start with: sudo systemctl start redis" && exit 1)
echo ""

# Clean up any previous test data
echo "Cleaning Redis test data..."
redis-cli DEL "cluster:workers" > /dev/null 2>&1 || true
redis-cli KEYS "cluster:worker:*" | xargs -r redis-cli DEL > /dev/null 2>&1 || true

# Kill any existing processes
echo "Cleaning up old processes..."
pkill -f "python.*cluster/master.py" 2>/dev/null || true
pkill -f "python.*cluster/worker.py" 2>/dev/null || true
sleep 1

echo ""
echo "Starting cluster components..."
echo ""

# Start master
echo "🚀 Starting Master (port 50051)..."
PYTHONPATH=/data/ch8-agent-cluster python cluster/master.py > /tmp/ch8-master.log 2>&1 &
MASTER_PID=$!
echo "   PID: $MASTER_PID"
sleep 2

# Start worker 1
echo "🚀 Starting Worker 1 (port 50052)..."
PYTHONPATH=/data/ch8-agent-cluster python cluster/worker.py config/worker.yaml > /tmp/ch8-worker1.log 2>&1 &
WORKER1_PID=$!
echo "   PID: $WORKER1_PID"
sleep 2

# Start worker 2
echo "🚀 Starting Worker 2 (port 50053)..."
PYTHONPATH=/data/ch8-agent-cluster python cluster/worker.py config/worker2.yaml > /tmp/ch8-worker2.log 2>&1 &
WORKER2_PID=$!
echo "   PID: $WORKER2_PID"
sleep 3

echo ""
echo "======================================"
echo "  Cluster Status"
echo "======================================"
echo ""

# Check processes
echo "Processes:"
ps aux | grep -E "cluster/(master|worker)" | grep -v grep || echo "  No processes found"
echo ""

# Check Redis workers
echo "Registered workers in Redis:"
redis-cli SMEMBERS "cluster:workers" 2>/dev/null | while read worker; do
    if [ -n "$worker" ]; then
        echo "  - $worker"
    fi
done

if [ $(redis-cli SCARD "cluster:workers" 2>/dev/null || echo 0) -eq 0 ]; then
    echo "  (No workers registered yet - they may still be starting)"
fi

echo ""
echo "======================================"
echo "  Logs"
echo "======================================"
echo ""
echo "Master log: /tmp/ch8-master.log"
echo "Worker 1 log: /tmp/ch8-worker1.log"
echo "Worker 2 log: /tmp/ch8-worker2.log"
echo ""
echo "View logs with:"
echo "  tail -f /tmp/ch8-master.log"
echo "  tail -f /tmp/ch8-worker1.log"
echo "  tail -f /tmp/ch8-worker2.log"
echo ""

echo "======================================"
echo "  Test Task Submission"
echo "======================================"
echo ""

# Test with Python
python3 <<EOF
import asyncio
import grpc
import sys
sys.path.insert(0, "/data/ch8-agent-cluster")

from cluster.proto import cluster_pb2, cluster_pb2_grpc
from cluster.master import MasterNode, TaskRequest
import yaml

async def test():
    # Load config
    with open("/data/ch8-agent-cluster/config/master.yaml") as f:
        config = yaml.safe_load(f)
    
    # Connect to running master's Redis
    from cluster.discovery import RedisDiscovery
    discovery = RedisDiscovery(
        redis_url=config["discovery"]["redis_url"],
        heartbeat_interval=10
    )
    await discovery.connect()
    
    # Check workers
    workers = await discovery.get_all_workers()
    print(f"Found {len(workers)} active workers:")
    for w in workers:
        print(f"  - {w['worker_id']} @ {w['address']}")
        print(f"    Capabilities: {', '.join(w['capabilities'])}")
    
    await discovery.disconnect()
    
    if len(workers) > 0:
        print("\n✅ Cluster is operational!")
    else:
        print("\n⚠️  No workers registered yet. Check logs.")

asyncio.run(test())
EOF

echo ""
echo "======================================"
echo "  Cleanup"
echo "======================================"
echo ""
echo "To stop all components:"
echo "  kill $MASTER_PID $WORKER1_PID $WORKER2_PID"
echo ""
echo "Or run:"
echo "  pkill -f 'python.*cluster/(master|worker)'"
echo ""

echo "Ready for testing! ✨"
