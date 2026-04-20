"""
Service Discovery using Redis

Workers register themselves with:
- worker_id
- address (host:port)
- capabilities
- status

Master maintains active worker registry.
"""
import redis.asyncio as redis
import json
import time
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger()


class RedisDiscovery:
    """Redis-based service discovery for cluster"""
    
    def __init__(self, redis_url: str, heartbeat_interval: int = 10):
        self.redis_url = redis_url
        self.heartbeat_interval = heartbeat_interval
        self.client: Optional[redis.Redis] = None
        self.worker_key_prefix = "cluster:worker:"
        self.worker_list_key = "cluster:workers"
        
    async def connect(self):
        """Connect to Redis"""
        self.client = await redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("redis_connected", url=self.redis_url)
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.aclose()
            logger.info("redis_disconnected")
    
    async def register_worker(self, worker_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Register a worker in Redis
        
        Args:
            worker_id: Unique worker identifier
            metadata: Worker info (address, capabilities, etc)
        """
        try:
            worker_key = f"{self.worker_key_prefix}{worker_id}"
            
            # Store worker metadata
            worker_data = {
                **metadata,
                "worker_id": worker_id,
                "registered_at": int(time.time()),
                "last_heartbeat": int(time.time()),
                "status": "active"
            }
            
            # Set worker data with expiry (2x heartbeat interval)
            await self.client.setex(
                worker_key,
                self.heartbeat_interval * 2,
                json.dumps(worker_data)
            )
            
            # Add to worker list (set)
            await self.client.sadd(self.worker_list_key, worker_id)
            
            logger.info("worker_registered", 
                       worker_id=worker_id,
                       capabilities=metadata.get("capabilities", []))
            return True
            
        except Exception as e:
            logger.error("worker_registration_failed",
                        worker_id=worker_id,
                        error=str(e))
            return False
    
    async def update_heartbeat(self, worker_id: str) -> bool:
        """Update worker heartbeat timestamp"""
        try:
            worker_key = f"{self.worker_key_prefix}{worker_id}"
            
            # Get existing data
            data = await self.client.get(worker_key)
            if not data:
                logger.warning("heartbeat_worker_not_found", worker_id=worker_id)
                return False
            
            worker_data = json.loads(data)
            worker_data["last_heartbeat"] = int(time.time())
            
            # Update with new expiry
            await self.client.setex(
                worker_key,
                self.heartbeat_interval * 2,
                json.dumps(worker_data)
            )
            
            logger.debug("heartbeat_updated", worker_id=worker_id)
            return True
            
        except Exception as e:
            logger.error("heartbeat_update_failed",
                        worker_id=worker_id,
                        error=str(e))
            return False
    
    async def unregister_worker(self, worker_id: str) -> bool:
        """Remove worker from registry"""
        try:
            worker_key = f"{self.worker_key_prefix}{worker_id}"
            
            # Delete worker data
            await self.client.delete(worker_key)
            
            # Remove from worker list
            await self.client.srem(self.worker_list_key, worker_id)
            
            logger.info("worker_unregistered", worker_id=worker_id)
            return True
            
        except Exception as e:
            logger.error("worker_unregistration_failed",
                        worker_id=worker_id,
                        error=str(e))
            return False
    
    async def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker metadata"""
        try:
            worker_key = f"{self.worker_key_prefix}{worker_id}"
            data = await self.client.get(worker_key)
            
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error("get_worker_failed",
                        worker_id=worker_id,
                        error=str(e))
            return None
    
    async def get_all_workers(self) -> List[Dict[str, Any]]:
        """Get all registered workers"""
        try:
            # Get all worker IDs
            worker_ids = await self.client.smembers(self.worker_list_key)
            
            workers = []
            for worker_id in worker_ids:
                worker = await self.get_worker(worker_id)
                if worker:
                    workers.append(worker)
                else:
                    # Clean up stale entry
                    await self.client.srem(self.worker_list_key, worker_id)
            
            return workers
            
        except Exception as e:
            logger.error("get_all_workers_failed", error=str(e))
            return []
    
    async def find_workers_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Find workers that have a specific capability"""
        workers = await self.get_all_workers()
        
        matching = [
            w for w in workers
            if capability in w.get("capabilities", [])
        ]
        
        logger.debug("capability_search",
                    capability=capability,
                    found=len(matching))
        
        return matching
    
    async def update_worker_status(self, worker_id: str, status: str, 
                                   active_tasks: int = 0,
                                   cpu_usage: float = 0.0,
                                   memory_usage: float = 0.0) -> bool:
        """Update worker runtime status"""
        try:
            worker_key = f"{self.worker_key_prefix}{worker_id}"
            
            data = await self.client.get(worker_key)
            if not data:
                return False
            
            worker_data = json.loads(data)
            worker_data.update({
                "status": status,
                "active_tasks": active_tasks,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "last_heartbeat": int(time.time())
            })
            
            await self.client.setex(
                worker_key,
                self.heartbeat_interval * 2,
                json.dumps(worker_data)
            )
            
            return True
            
        except Exception as e:
            logger.error("status_update_failed",
                        worker_id=worker_id,
                        error=str(e))
            return False
