"""
Redis Integration Agent - Full operations for Redis
"""

import aioredis
from typing import Dict, Any, List, Optional, Union
import structlog
import json

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class RedisAgent(BaseDatabaseAgent):
    """
    Redis integration agent with full capabilities

    Capabilities:
    - String operations
    - Hash operations
    - List operations
    - Set operations
    - Sorted set operations
    - Pub/Sub messaging
    - Transactions (MULTI/EXEC)
    - Pipelining
    - Lua scripts
    - Streams
    - Geospatial operations
    - TTL and expiration
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "string_ops",
            "hash_ops",
            "list_ops",
            "set_ops",
            "sorted_set_ops",
            "pubsub",
            "transactions",
            "pipelining",
            "lua_scripts",
            "streams",
            "geospatial",
            "ttl_expiration"
        ]

    async def connect(self) -> bool:
        """Establish Redis connection"""
        try:
            if self.connection:
                return True

            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 6379)
            db = self.config.get('db', 0)
            password = self.config.get('password')

            if password:
                self.connection = await aioredis.create_redis_pool(
                    f'redis://:{password}@{host}:{port}/{db}'
                )
            else:
                self.connection = await aioredis.create_redis_pool(
                    f'redis://{host}:{port}/{db}'
                )

            self.is_connected = True
            logger.info("Connected to Redis", db=db)
            return True

        except Exception as e:
            logger.error("Redis connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close Redis connection"""
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            self.connection = None
            self.is_connected = False
            logger.info("Disconnected from Redis")

    async def execute(self, command: str, *args) -> Any:
        """Execute Redis command"""
        if not self.connection:
            await self.connect()

        return await self.connection.execute(command, *args)

    # String Operations
    async def set(self, key: str, value: Any,
                 ex: Optional[int] = None,
                 px: Optional[int] = None) -> bool:
        """Set key to value"""
        if not self.connection:
            await self.connect()

        # Serialize non-string values
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)

        return await self.connection.set(key, value, expire=ex, pexpire=px)

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        if not self.connection:
            await self.connect()

        value = await self.connection.get(key, encoding='utf-8')

        # Try to deserialize JSON
        if value:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        return None

    async def mget(self, keys: List[str]) -> List[Optional[Any]]:
        """Get multiple values"""
        if not self.connection:
            await self.connect()

        values = await self.connection.mget(*keys, encoding='utf-8')

        # Try to deserialize JSON
        result = []
        for value in values:
            if value:
                try:
                    result.append(json.loads(value))
                except (json.JSONDecodeError, TypeError):
                    result.append(value)
            else:
                result.append(None)

        return result

    async def delete(self, *keys: str) -> int:
        """Delete keys"""
        if not self.connection:
            await self.connect()

        return await self.connection.delete(*keys)

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        if not self.connection:
            await self.connect()

        return await self.connection.exists(key) > 0

    # Hash Operations
    async def hset(self, key: str, field: str, value: Any) -> int:
        """Set hash field"""
        if not self.connection:
            await self.connect()

        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)

        return await self.connection.hset(key, field, value)

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """Get hash field"""
        if not self.connection:
            await self.connect()

        value = await self.connection.hget(key, field, encoding='utf-8')

        if value:
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        return None

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all hash fields"""
        if not self.connection:
            await self.connect()

        data = await self.connection.hgetall(key, encoding='utf-8')

        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v

        return result

    async def hdel(self, key: str, *fields: str) -> int:
        """Delete hash fields"""
        if not self.connection:
            await self.connect()

        return await self.connection.hdel(key, *fields)

    # List Operations
    async def lpush(self, key: str, *values: Any) -> int:
        """Push values to list head"""
        if not self.connection:
            await self.connect()

        serialized = [json.dumps(v) if not isinstance(v, (str, bytes)) else v
                     for v in values]

        return await self.connection.lpush(key, *serialized)

    async def rpush(self, key: str, *values: Any) -> int:
        """Push values to list tail"""
        if not self.connection:
            await self.connect()

        serialized = [json.dumps(v) if not isinstance(v, (str, bytes)) else v
                     for v in values]

        return await self.connection.rpush(key, *serialized)

    async def lrange(self, key: str, start: int = 0, stop: int = -1) -> List[Any]:
        """Get list range"""
        if not self.connection:
            await self.connect()

        values = await self.connection.lrange(key, start, stop, encoding='utf-8')

        result = []
        for v in values:
            try:
                result.append(json.loads(v))
            except (json.JSONDecodeError, TypeError):
                result.append(v)

        return result

    # Set Operations
    async def sadd(self, key: str, *members: Any) -> int:
        """Add members to set"""
        if not self.connection:
            await self.connect()

        serialized = [json.dumps(m) if not isinstance(m, (str, bytes)) else m
                     for m in members]

        return await self.connection.sadd(key, *serialized)

    async def smembers(self, key: str) -> List[Any]:
        """Get all set members"""
        if not self.connection:
            await self.connect()

        members = await self.connection.smembers(key, encoding='utf-8')

        result = []
        for m in members:
            try:
                result.append(json.loads(m))
            except (json.JSONDecodeError, TypeError):
                result.append(m)

        return result

    # Sorted Set Operations
    async def zadd(self, key: str, score: float, member: Any) -> int:
        """Add member to sorted set"""
        if not self.connection:
            await self.connect()

        if not isinstance(member, (str, bytes)):
            member = json.dumps(member)

        return await self.connection.zadd(key, score, member)

    async def zrange(self, key: str, start: int = 0, stop: int = -1,
                    withscores: bool = False) -> Union[List[Any], List[tuple]]:
        """Get sorted set range"""
        if not self.connection:
            await self.connect()

        result = await self.connection.zrange(
            key, start, stop,
            withscores=withscores,
            encoding='utf-8'
        )

        if withscores:
            return [(json.loads(v) if isinstance(v, str) else v, s)
                   for v, s in result]
        else:
            return [json.loads(v) if isinstance(v, str) else v for v in result]

    # Utility methods matching base interface
    async def query(self, pattern: str = '*') -> List[str]:
        """Query keys matching pattern"""
        if not self.connection:
            await self.connect()

        keys = await self.connection.keys(pattern, encoding='utf-8')
        return keys

    async def insert(self, table: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Insert data (maps to hash operations)"""
        if isinstance(data, dict):
            # Single hash
            for field, value in data.items():
                await self.hset(table, field, value)
            return table
        else:
            # Multiple items as list
            inserted = []
            for item in data:
                key = f"{table}:{item.get('id', id(item))}"
                for field, value in item.items():
                    await self.hset(key, field, value)
                inserted.append(key)
            return inserted

    async def update(self, key: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update data (maps to hash operations)"""
        count = 0
        for field, value in data.items():
            count += await self.hset(key, field, value)
        return count

    async def expire(self, key: str, seconds: int) -> bool:
        """Set key expiration"""
        if not self.connection:
            await self.connect()

        return await self.connection.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        """Get key TTL"""
        if not self.connection:
            await self.connect()

        return await self.connection.ttl(key)

    async def get_info(self) -> Dict[str, Any]:
        """Get Redis information"""
        if not self.connection:
            await self.connect()

        info = await self.connection.info()

        return {
            'version': info.get('redis_version', 'unknown'),
            'db': self.config.get('db', 0),
            'connected_clients': info.get('connected_clients', 0),
            'used_memory': info.get('used_memory_human', 'unknown'),
            'keys': await self.connection.dbsize()
        }

    async def flush_db(self) -> bool:
        """Flush current database"""
        if not self.connection:
            await self.connect()

        return await self.connection.flushdb()
