"""
Worker Node - Executes tasks delegated by master

Responsibilities:
- Register with master on startup
- Expose local capabilities via MCP
- Execute tasks received from master
- Report results back to master
- Spawn and manage local subagents
"""
import asyncio
import grpc
import time
import psutil
from concurrent import futures
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import structlog

from cluster.proto import cluster_pb2, cluster_pb2_grpc

logger = structlog.get_logger()


class WorkerCapability(BaseModel):
    """Describes a capability this worker can provide"""
    name: str
    description: str
    mcp_server_url: Optional[str] = None


class WorkerServicer(cluster_pb2_grpc.WorkerServiceServicer):
    """gRPC service implementation for Worker"""
    
    def __init__(self, worker_node: 'WorkerNode'):
        self.worker = worker_node
    
    async def AssignTask(self, request, context):
        """Handle task assignment from master"""
        logger.info("task_assignment_received",
                   task_id=request.task_id,
                   description=request.description[:50])
        
        # Check if we can accept more tasks
        if len(self.worker.active_tasks) >= self.worker.max_concurrent_tasks:
            return cluster_pb2.TaskAck(
                accepted=False,
                message="Worker at max capacity"
            )
        
        # Accept task and execute asynchronously
        asyncio.create_task(
            self.worker.execute_task(
                task_id=request.task_id,
                description=request.description,
                priority=request.priority,
                context=dict(request.context)
            )
        )
        
        return cluster_pb2.TaskAck(
            accepted=True,
            message="Task accepted"
        )
    
    async def GetStatus(self, request, context):
        """Return worker status"""
        return cluster_pb2.WorkerStatus(
            worker_id=self.worker.node_id,
            status="active" if len(self.worker.active_tasks) > 0 else "idle",
            active_tasks=len(self.worker.active_tasks),
            completed_tasks=self.worker.completed_tasks,
            failed_tasks=self.worker.failed_tasks,
            cpu_usage=psutil.cpu_percent(),
            memory_usage=psutil.virtual_memory().percent
        )
    
    async def CancelTask(self, request, context):
        """Handle task cancellation"""
        logger.info("task_cancellation_received",
                   task_id=request.task_id,
                   reason=request.reason)
        
        # TODO: Implement task cancellation
        return cluster_pb2.Ack(
            ok=True,
            message="Cancellation not yet implemented"
        )


class WorkerNode:
    """
    Worker node that executes tasks assigned by master
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.node_id = config.get("node_id", "worker-001")
        self.master_url = config.get("master_url")
        self.grpc_port = config.get("grpc_port", 50052)
        self.max_concurrent_tasks = config.get("max_concurrent_tasks", 5)
        
        self.capabilities: list[WorkerCapability] = []
        self.active_tasks: Dict[str, Any] = {}
        self.completed_tasks = 0
        self.failed_tasks = 0
        
        # gRPC
        self.grpc_server: Optional[grpc.aio.Server] = None
        self.master_channel: Optional[grpc.aio.Channel] = None
        self.master_stub: Optional[cluster_pb2_grpc.MasterServiceStub] = None
        
        logger.info("worker_node_initialized",
                   node_id=self.node_id,
                   master_url=self.master_url)
    
    async def start(self):
        """Start worker node services"""
        logger.info("starting_worker_node")
        
        # Discover local capabilities
        await self._discover_capabilities()
        
        # Start gRPC server (for receiving tasks)
        await self._start_grpc_server()
        
        # Connect to master
        await self._connect_to_master()
        
        # Register with master
        await self._register_with_master()
        
        # Start heartbeat loop
        asyncio.create_task(self._heartbeat_loop())
        
        logger.info("worker_node_ready",
                   grpc_port=self.grpc_port,
                   capabilities=len(self.capabilities))
    
    async def _discover_capabilities(self):
        """Discover what capabilities this node can provide"""
        logger.info("discovering_capabilities")
        
        # For now, hardcoded capabilities
        # TODO: Dynamically discover from installed MCP servers
        self.capabilities = [
            WorkerCapability(
                name="general_agent",
                description="General purpose agent execution",
            ),
            WorkerCapability(
                name="python_execution",
                description="Execute Python code",
            ),
        ]
        
        logger.info("capabilities_discovered", count=len(self.capabilities))
    
    async def _start_grpc_server(self):
        """Start gRPC server to receive tasks from master"""
        self.grpc_server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=10)
        )
        
        cluster_pb2_grpc.add_WorkerServiceServicer_to_server(
            WorkerServicer(self),
            self.grpc_server
        )
        
        listen_addr = f"0.0.0.0:{self.grpc_port}"
        self.grpc_server.add_insecure_port(listen_addr)
        
        await self.grpc_server.start()
        logger.info("grpc_server_started", address=listen_addr)
    
    async def _connect_to_master(self):
        """Connect to master node"""
        logger.info("connecting_to_master", master_url=self.master_url)
        
        # Extract address from URL (remove grpc:// prefix)
        master_address = self.master_url.replace("grpc://", "")
        
        self.master_channel = grpc.aio.insecure_channel(master_address)
        self.master_stub = cluster_pb2_grpc.MasterServiceStub(self.master_channel)
        
        logger.info("master_connection_established")
    
    async def _register_with_master(self):
        """Register with master node"""
        logger.info("registering_with_master")
        
        # Get our external address
        # For local testing, use localhost:port
        # In production, should be actual network address
        worker_address = f"localhost:{self.grpc_port}"
        
        try:
            response = await self.master_stub.RegisterWorker(
                cluster_pb2.WorkerRegistration(
                    worker_id=self.node_id,
                    capabilities=[c.name for c in self.capabilities],
                    address=worker_address,
                    max_concurrent_tasks=self.max_concurrent_tasks
                ),
                timeout=10
            )
            
            if response.success:
                logger.info("registration_successful",
                          heartbeat_interval=response.heartbeat_interval_seconds)
                self.heartbeat_interval = response.heartbeat_interval_seconds
            else:
                logger.error("registration_failed", message=response.message)
                raise Exception(f"Registration failed: {response.message}")
                
        except Exception as e:
            logger.error("registration_error", error=str(e))
            raise
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to master"""
        logger.info("heartbeat_loop_started",
                   interval=self.heartbeat_interval)
        
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                response = await self.master_stub.Heartbeat(
                    cluster_pb2.HeartbeatRequest(
                        worker_id=self.node_id,
                        active_tasks=len(self.active_tasks),
                        cpu_usage=psutil.cpu_percent(),
                        memory_usage=psutil.virtual_memory().percent
                    ),
                    timeout=5
                )
                
                logger.debug("heartbeat_sent",
                           active_tasks=len(self.active_tasks))
                
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))
                # Continue trying
    
    async def execute_task(self, task_id: str, description: str,
                          priority: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task assigned by master
        
        Returns:
            Result dictionary with status and output
        """
        logger.info("executing_task",
                   task_id=task_id,
                   description=description[:100])
        
        start_time = time.time()
        
        # Track task
        self.active_tasks[task_id] = {
            "description": description,
            "started_at": start_time
        }
        
        try:
            # Simple execution: just echo the task
            # In real implementation, this would:
            # 1. Analyze task complexity
            # 2. Spawn subagent if needed
            # 3. Execute with appropriate model
            # 4. Return structured result
            
            # Simulate work
            await asyncio.sleep(2)
            
            output = f"Task completed: {description[:100]}"
            
            result = {
                "status": "success",
                "output": output
            }
            
            self.completed_tasks += 1
            
            # Report result to master
            await self._report_result(
                task_id=task_id,
                success=True,
                output=output,
                error="",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
            
            return result
            
        except Exception as e:
            logger.error("task_execution_failed",
                        task_id=task_id,
                        error=str(e))
            
            self.failed_tasks += 1
            
            # Report failure to master
            await self._report_result(
                task_id=task_id,
                success=False,
                output="",
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
            
            return {
                "status": "error",
                "error": str(e)
            }
            
        finally:
            # Remove from active tasks
            self.active_tasks.pop(task_id, None)
    
    async def _report_result(self, task_id: str, success: bool,
                            output: str, error: str, execution_time_ms: int):
        """Report task result to master"""
        try:
            await self.master_stub.ReportTaskResult(
                cluster_pb2.TaskResult(
                    task_id=task_id,
                    worker_id=self.node_id,
                    success=success,
                    output=output,
                    error=error,
                    execution_time_ms=execution_time_ms
                ),
                timeout=10
            )
            
            logger.info("result_reported",
                       task_id=task_id,
                       success=success)
            
        except Exception as e:
            logger.error("result_report_failed",
                        task_id=task_id,
                        error=str(e))
    
    async def stop(self):
        """Shutdown worker node"""
        logger.info("shutting_down_worker")
        
        if self.grpc_server:
            await self.grpc_server.stop(grace=5)
        
        if self.master_channel:
            await self.master_channel.close()


async def main():
    """Entry point for worker node"""
    import yaml
    import sys
    
    if len(sys.argv) < 2:
        config_file = "config/worker.yaml"
    else:
        config_file = sys.argv[1]
    
    # Load config
    with open(config_file) as f:
        config = yaml.safe_load(f)
    
    # Add default values
    config.setdefault("grpc_port", 50052)
    config.setdefault("max_concurrent_tasks", 5)
    
    # Create and start worker
    worker = WorkerNode(config)
    await worker.start()
    
    # Keep running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
