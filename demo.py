#!/usr/bin/env python3
"""
Demo Script - Test CH8 Agent Cluster End-to-End

Demonstrates:
1. Starting master node
2. Starting 2 worker nodes
3. Submitting tasks to master
4. Watching task execution and results
"""
import asyncio
import sys
import time
from typing import List
import structlog

# Add cluster to path
sys.path.insert(0, "/data/ch8-agent-cluster")

from cluster.master import MasterNode, TaskRequest
import yaml

# Setup logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()


async def run_demo():
    """Run full cluster demo"""
    
    print("\n" + "="*70)
    print("  CH8 Agent Cluster - Sprint 1 Demo")
    print("="*70 + "\n")
    
    # Load master config
    with open("/data/ch8-agent-cluster/config/master.yaml") as f:
        master_config = yaml.safe_load(f)
    
    print("📍 Step 1: Starting Master Node...")
    master = MasterNode(master_config)
    await master.start()
    print("✅ Master node running on port 50051\n")
    
    # Wait for master to be ready
    await asyncio.sleep(2)
    
    print("📍 Step 2: Starting Worker Nodes...")
    print("   (Workers will be started separately in other terminals)")
    print("   Run these commands in separate terminals:")
    print("   Terminal 2: cd /data/ch8-agent-cluster && source venv/bin/activate && python cluster/worker.py config/worker.yaml")
    print("   Terminal 3: cd /data/ch8-agent-cluster && source venv/bin/activate && python cluster/worker.py config/worker2.yaml")
    print("\nWaiting 10 seconds for workers to connect...")
    
    for i in range(10, 0, -1):
        print(f"   {i}...", end="\r", flush=True)
        await asyncio.sleep(1)
    
    print("\n")
    
    # Check registered workers
    workers = await master.discovery.get_all_workers()
    print(f"📊 Registered Workers: {len(workers)}")
    for worker in workers:
        print(f"   - {worker['worker_id']} @ {worker['address']}")
        print(f"     Capabilities: {', '.join(worker['capabilities'])}")
    print()
    
    if len(workers) == 0:
        print("⚠️  No workers registered! Make sure to start workers in separate terminals.")
        print("   Demo will continue anyway to show master functionality.")
        print()
    
    # Submit test tasks
    print("📍 Step 3: Submitting Test Tasks...")
    
    test_tasks = [
        TaskRequest(
            task_id="task-001",
            description="Analyze the sentiment of this text: 'I love distributed systems!'",
            priority=1,
            required_capabilities=["general_agent"]
        ),
        TaskRequest(
            task_id="task-002",
            description="Calculate the fibonacci sequence up to n=10",
            priority=2,
            required_capabilities=["python_execution"]
        ),
        TaskRequest(
            task_id="task-003",
            description="Summarize the benefits of microservices architecture",
            priority=3,
            required_capabilities=["general_agent"]
        ),
    ]
    
    submitted_ids = []
    for task in test_tasks:
        task_id = await master.submit_task(task)
        submitted_ids.append(task_id)
        print(f"   ✓ Submitted: {task_id} - {task.description[:50]}...")
    
    print(f"\n   Total tasks submitted: {len(submitted_ids)}\n")
    
    # Monitor task execution
    print("📍 Step 4: Monitoring Task Execution...")
    print("   (Watching for 30 seconds...)\n")
    
    start_time = time.time()
    last_status = {}
    
    while time.time() - start_time < 30:
        # Check task statuses
        current_status = {}
        for task_id in submitted_ids:
            status = await master.get_task_status(task_id)
            if status:
                current_status[task_id] = status["status"]
                
                # Print status changes
                if task_id not in last_status or last_status[task_id] != status["status"]:
                    print(f"   [{time.strftime('%H:%M:%S')}] {task_id}: {last_status.get(task_id, 'unknown')} → {status['status']}")
                    
                    if status["status"] == "completed":
                        result = status.get("result", {})
                        print(f"      ✅ Output: {result.get('output', 'N/A')[:60]}...")
                        print(f"      ⏱️  Execution time: {result.get('execution_time_ms', 0)}ms")
                        print()
        
        last_status = current_status
        
        # Check if all completed
        if all(current_status.get(tid) in ["completed", "failed"] for tid in submitted_ids):
            print("\n   All tasks completed!\n")
            break
        
        await asyncio.sleep(1)
    
    # Final status report
    print("="*70)
    print("  Final Status Report")
    print("="*70 + "\n")
    
    completed = 0
    failed = 0
    pending = 0
    
    for task_id in submitted_ids:
        status = await master.get_task_status(task_id)
        if status:
            task_status = status["status"]
            if task_status == "completed":
                completed += 1
            elif task_status == "failed":
                failed += 1
            else:
                pending += 1
            
            print(f"📋 {task_id}:")
            print(f"   Status: {task_status}")
            print(f"   Worker: {status.get('assigned_worker', 'N/A')}")
            if status.get("result"):
                result = status["result"]
                print(f"   Success: {result.get('success', False)}")
                print(f"   Time: {result.get('execution_time_ms', 0)}ms")
            print()
    
    print(f"Summary: ✅ {completed} completed | ❌ {failed} failed | ⏳ {pending} pending\n")
    
    # Worker stats
    workers = await master.discovery.get_all_workers()
    print("Worker Status:")
    for worker in workers:
        print(f"   {worker['worker_id']}:")
        print(f"      Active tasks: {worker.get('active_tasks', 0)}")
        print(f"      CPU: {worker.get('cpu_usage', 0):.1f}%")
        print(f"      Memory: {worker.get('memory_usage', 0):.1f}%")
    
    print("\n" + "="*70)
    print("  Demo Complete! ✨")
    print("="*70 + "\n")
    
    print("Press Ctrl+C to stop master...")
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await master.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
