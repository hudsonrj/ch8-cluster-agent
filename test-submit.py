#!/usr/bin/env python3
"""
Simple test - Submit tasks to running cluster
"""
import asyncio
import sys
sys.path.insert(0, "/data/ch8-agent")

from cluster.master import TaskRequest
from cluster.discovery import RedisDiscovery
import grpc
from cluster.proto import cluster_pb2, cluster_pb2_grpc


async def submit_tasks():
    """Submit test tasks to cluster"""
    
    print("\n" + "="*60)
    print("  Testing Task Submission")
    print("="*60 + "\n")
    
    # Connect to Redis to check workers
    discovery = RedisDiscovery(
        redis_url="redis://:1q2w3e4r@127.0.0.1:6379/0",
        heartbeat_interval=10
    )
    await discovery.connect()
    
    workers = await discovery.get_all_workers()
    print(f"📊 Found {len(workers)} active workers\n")
    
    if len(workers) == 0:
        print("❌ No workers available! Start workers first.")
        await discovery.disconnect()
        return
    
    # Create tasks directly via gRPC to master
    async with grpc.aio.insecure_channel('localhost:50051') as channel:
        # We'll submit tasks by directly contacting a worker for testing
        # In production, you'd have a client API that talks to master
        pass
    
    # For now, let's just send tasks directly to a worker for testing
    worker = workers[0]
    print(f"📤 Sending test task to: {worker['worker_id']}\n")
    
    async with grpc.aio.insecure_channel(worker['address']) as channel:
        stub = cluster_pb2_grpc.WorkerServiceStub(channel)
        
        # Test 1: Simple task
        print("Test 1: Simple task")
        response = await stub.AssignTask(
            cluster_pb2.TaskAssignment(
                task_id="test-001",
                description="Calculate 2+2 and explain the result",
                priority=1,
                context={},
                timeout_seconds=60
            )
        )
        print(f"   Response: accepted={response.accepted}, message={response.message}")
        
        # Wait for execution
        await asyncio.sleep(3)
        
        # Check status
        status_response = await stub.GetStatus(
            cluster_pb2.StatusRequest(worker_id=worker['worker_id'])
        )
        print(f"   Worker status: {status_response.status}")
        print(f"   Completed tasks: {status_response.completed_tasks}")
        print()
        
        # Test 2: Another task
        print("Test 2: Another task")
        response = await stub.AssignTask(
            cluster_pb2.TaskAssignment(
                task_id="test-002",
                description="List 5 benefits of distributed systems",
                priority=2,
                context={},
                timeout_seconds=60
            )
        )
        print(f"   Response: accepted={response.accepted}, message={response.message}")
        
        await asyncio.sleep(3)
        
        # Final status
        status_response = await stub.GetStatus(
            cluster_pb2.StatusRequest(worker_id=worker['worker_id'])
        )
        print(f"   Worker status: {status_response.status}")
        print(f"   Completed tasks: {status_response.completed_tasks}")
        print()
    
    await discovery.disconnect()
    
    print("="*60)
    print("✅ Test completed!")
    print("="*60 + "\n")
    print("Check logs for task execution:")
    print("  tail /tmp/ch8-master.log")
    print("  tail /tmp/ch8-worker1.log")
    print("  tail /tmp/ch8-worker2.log")
    print()


if __name__ == "__main__":
    asyncio.run(submit_tasks())
