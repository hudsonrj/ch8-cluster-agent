#!/bin/bash
# Shutdown script - Stop all cluster components

echo "🛑 Stopping CH8 Agent Cluster..."
echo ""

# Kill processes
pkill -9 -f "python.*cluster/master.py" 2>/dev/null && echo "✓ Master stopped" || echo "  (Master not running)"
pkill -9 -f "python.*cluster/worker.py" 2>/dev/null && echo "✓ Workers stopped" || echo "  (Workers not running)"

# Optional: Clean Redis data
read -p "Clean Redis data? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    redis-cli -a 1q2w3e4r DEL "cluster:workers" > /dev/null 2>&1
    redis-cli -a 1q2w3e4r KEYS "cluster:worker:*" | xargs -r redis-cli -a 1q2w3e4r DEL > /dev/null 2>&1
    echo "✓ Redis data cleaned"
fi

echo ""
echo "Cluster stopped."
