"""
Master Node - Coordinates the entire cluster

Responsibilities:
- Accept tasks from users/APIs
- Analyze task requirements
- Route tasks to appropriate worker nodes
- Aggregate results
- Maintain cluster health
"""
import asyncio
import grpc
import time
from concurrent import futures
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import structlog

from cluster.proto import cluster_pb2, cluster_pb2_grpc
from cluster.discovery import RedisDiscovery

logger = structlog.get_logger()


class TaskRequest(BaseModel):
    """Incoming task from user"""
    task_id: str
    description: str
    priority: int = 3  # 1=highest, 5=lowest
    required_capabilities: list[str] = []
    context: Dict[str, Any] = {}


class TaskRecord:
    """Track task state"""
    def __init__(self, task_id: str, task: TaskRequest):
        self.task_id = task_id
        self.task = task
        self.assigned_worker: Optional[str] = None
        self.status = "pending"  # pending, assigned, running, completed, failed
        self.result: Optional[Dict[str, Any]] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None


class MasterServicer(cluster_pb2_grpc.MasterServiceServicer):
    """gRPC service implementation for Master"""
    
    def __init__(self, master_node: 'MasterNode'):
        self.master = master_node
    
    async def RegisterWorker(self, request, context):
        """Handle worker registration"""
        logger.info("worker_registration_request",
                   worker_id=request.worker_id,
                   capabilities=list(request.capabilities))
        
        success = await self.master.register_worker(
            worker_id=request.worker_id,
            capabilities=list(request.capabilities),
            address=request.address,
            max_concurrent_tasks=request.max_concurrent_tasks
        )
        
        if success:
            return cluster_pb2.RegistrationResponse(
                success=True,
                message="Registration successful",
                heartbeat_interval_seconds=self.master.heartbeat_interval
            )
        else:
            return cluster_pb2.RegistrationResponse(
                success=False,
                message="Registration failed",
                heartbeat_interval_seconds=0
            )
    
    async def Heartbeat(self, request, context):
        """Handle worker heartbeat"""
        logger.debug("heartbeat_received",
                    worker_id=request.worker_id,
                    active_tasks=request.active_tasks)
        
        await self.master.process_heartbeat(
            worker_id=request.worker_id,
            active_tasks=request.active_tasks,
            cpu_usage=request.cpu_usage,
            memory_usage=request.memory_usage
        )
        
        return cluster_pb2.HeartbeatResponse(
            ok=True,
            next_heartbeat_seconds=self.master.heartbeat_interval
        )
    
    async def ReportTaskResult(self, request, context):
        """Handle task result from worker"""
        logger.info("task_result_received",
                   task_id=request.task_id,
                   worker_id=request.worker_id,
                   success=request.success)
        
        await self.master.handle_task_result(
            task_id=request.task_id,
            worker_id=request.worker_id,
            success=request.success,
            output=request.output,
            error=request.error,
            execution_time_ms=request.execution_time_ms
        )
        
        return cluster_pb2.Ack(ok=True, message="Result received")


class MasterNode:
    """
    Master node that coordinates distributed agent cluster
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.node_id = config.get("node_id", "master-001")
        self.grpc_port = config.get("grpc_port", 50051)
        self.heartbeat_interval = config["discovery"]["heartbeat_interval_seconds"]
        
        # Service discovery
        self.discovery = RedisDiscovery(
            redis_url=config["discovery"]["redis_url"],
            heartbeat_interval=self.heartbeat_interval
        )
        
        # Task management
        self.tasks: Dict[str, TaskRecord] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        
        # gRPC server
        self.grpc_server: Optional[grpc.aio.Server] = None
        
        logger.info("master_node_initialized", node_id=self.node_id)
    
    async def start(self):
        """Start master node services"""
        logger.info("starting_master_node")
        
        # Connect to Redis
        await self.discovery.connect()
        
        # Start gRPC server
        await self._start_grpc_server()
        
        # Start task dispatcher
        asyncio.create_task(self._task_dispatcher_loop())
        
        logger.info("master_node_ready",
                   grpc_port=self.grpc_port,
                   redis_url=self.config["discovery"]["redis_url"])
    
    async def _start_grpc_server(self):
        """Start gRPC server for worker connections"""
        self.grpc_server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=10)
        )
        
        cluster_pb2_grpc.add_MasterServiceServicer_to_server(
            MasterServicer(self),
            self.grpc_server
        )
        
        listen_addr = f"0.0.0.0:{self.grpc_port}"
        self.grpc_server.add_insecure_port(listen_addr)
        
        await self.grpc_server.start()
        logger.info("grpc_server_started", address=listen_addr)
    
    async def _task_dispatcher_loop(self):
        """Task dispatcher main loop"""
        logger.info("task_dispatcher_started")
        
        while True:
            try:
                # Get task from queue
                task = await self.task_queue.get()
                
                logger.info("dispatching_task", task_id=task.task_id)
                
                # Select worker
                worker_id = await self.select_worker(task.required_capabilities)
                
                if worker_id:
                    # Assign task to worker
                    success = await self._assign_task_to_worker(worker_id, task)
                    
                    if success:
                        task_record = self.tasks.get(task.task_id)
                        if task_record:
                            task_record.status = "assigned"
                            task_record.assigned_worker = worker_id
                    else:
                        # Re-queue if assignment failed
                        logger.warning("task_assignment_failed_requeuing",
                                     task_id=task.task_id)
                        await asyncio.sleep(1)
                        await self.task_queue.put(task)
                else:
                    # No suitable worker, re-queue
                    logger.warning("no_suitable_worker_requeuing",
                                 task_id=task.task_id,
                                 required_capabilities=task.required_capabilities)
                    await asyncio.sleep(2)
                    await self.task_queue.put(task)
                    
            except Exception as e:
                logger.error("task_dispatcher_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _assign_task_to_worker(self, worker_id: str, task: TaskRequest) -> bool:
        """Send task assignment to worker via gRPC"""
        try:
            worker = await self.discovery.get_worker(worker_id)
            if not worker:
                logger.error("worker_not_found", worker_id=worker_id)
                return False
            
            # Connect to worker
            address = worker["address"]
            async with grpc.aio.insecure_channel(address) as channel:
                stub = cluster_pb2_grpc.WorkerServiceStub(channel)
                
                # Send task assignment
                response = await stub.AssignTask(
                    cluster_pb2.TaskAssignment(
                        task_id=task.task_id,
                        description=task.description,
                        priority=task.priority,
                        context={k: str(v) for k, v in task.context.items()},
                        timeout_seconds=300
                    ),
                    timeout=10
                )
                
                if response.accepted:
                    logger.info("task_assigned",
                              task_id=task.task_id,
                              worker_id=worker_id)
                    return True
                else:
                    logger.warning("task_rejected",
                                 task_id=task.task_id,
                                 worker_id=worker_id,
                                 reason=response.message)
                    return False
                    
        except Exception as e:
            logger.error("task_assignment_error",
                        task_id=task.task_id,
                        worker_id=worker_id,
                        error=str(e))
            return False
    
    async def submit_task(self, task: TaskRequest) -> str:
        """
        Submit a task to the cluster
        
        Returns:
            task_id for tracking
        """
        logger.info("task_submitted",
                   task_id=task.task_id,
                   description=task.description[:50])
        
        # Create task record
        task_record = TaskRecord(task.task_id, task)
        self.tasks[task.task_id] = task_record
        
        # Add to queue
        await self.task_queue.put(task)
        
        return task.task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        task_record = self.tasks.get(task_id)
        if not task_record:
            return None
        
        return {
            "task_id": task_id,
            "status": task_record.status,
            "assigned_worker": task_record.assigned_worker,
            "created_at": task_record.created_at,
            "completed_at": task_record.completed_at,
            "result": task_record.result
        }
    
    async def register_worker(self, worker_id: str, capabilities: List[str],
                             address: str, max_concurrent_tasks: int) -> bool:
        """Register a new worker node"""
        metadata = {
            "capabilities": capabilities,
            "address": address,
            "max_concurrent_tasks": max_concurrent_tasks,
            "active_tasks": 0
        }
        
        success = await self.discovery.register_worker(worker_id, metadata)
        
        if success:
            logger.info("worker_registered",
                       worker_id=worker_id,
                       capabilities=capabilities,
                       address=address)
        
        return success
    
    async def process_heartbeat(self, worker_id: str, active_tasks: int,
                               cpu_usage: float, memory_usage: float):
        """Process worker heartbeat"""
        await self.discovery.update_worker_status(
            worker_id=worker_id,
            status="active",
            active_tasks=active_tasks,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage
        )
    
    async def handle_task_result(self, task_id: str, worker_id: str,
                                success: bool, output: str, error: str,
                                execution_time_ms: int):
        """Handle task completion from worker"""
        task_record = self.tasks.get(task_id)
        if not task_record:
            logger.warning("task_result_for_unknown_task", task_id=task_id)
            return
        
        task_record.status = "completed" if success else "failed"
        task_record.completed_at = time.time()
        task_record.result = {
            "success": success,
            "output": output,
            "error": error,
            "execution_time_ms": execution_time_ms,
            "worker_id": worker_id
        }
        
        logger.info("task_completed",
                   task_id=task_id,
                   success=success,
                   worker_id=worker_id,
                   execution_time_ms=execution_time_ms)
    
    async def select_worker(self, required_capabilities: List[str]) -> Optional[str]:
        """
        Select best worker for a task based on capabilities and load
        
        Returns:
            worker_id or None if no suitable worker found
        """
        workers = await self.discovery.get_all_workers()
        
        if not workers:
            logger.warning("no_workers_available")
            return None
        
        # Filter by capabilities
        suitable_workers = []
        for worker in workers:
            worker_caps = set(worker.get("capabilities", []))
            required_caps = set(required_capabilities)
            
            if not required_capabilities or required_caps.issubset(worker_caps):
                suitable_workers.append(worker)
        
        if not suitable_workers:
            logger.warning("no_workers_with_required_capabilities",
                         required=required_capabilities)
            return None
        
        # Select worker with lowest load
        selected = min(suitable_workers,
                      key=lambda w: w.get("active_tasks", 0))
        
        logger.info("worker_selected",
                   worker_id=selected["worker_id"],
                   active_tasks=selected.get("active_tasks", 0))
        
        return selected["worker_id"]
    
    async def stop(self):
        """Shutdown master node"""
        logger.info("shutting_down_master")
        
        if self.grpc_server:
            await self.grpc_server.stop(grace=5)
        
        await self.discovery.disconnect()


async def main():
    """Entry point for master node"""
    import yaml
    
    # Load config
    with open("config/master.yaml") as f:
        config = yaml.safe_load(f)
    
    # Create and start master
    master = MasterNode(config)
    await master.start()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await master.stop()


if __name__ == "__main__":
    asyncio.run(main())
