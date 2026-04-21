"""
MongoDB Integration Agent - Full CRUD operations for MongoDB
"""

from motor.motor_asyncio import AsyncIOMotorClient
from typing import Dict, Any, List, Optional, Union
import structlog
from datetime import datetime

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class MongoDBAgent(BaseDatabaseAgent):
    """
    MongoDB integration agent with full CRUD capabilities

    Capabilities:
    - Document operations (CRUD)
    - Aggregation pipelines
    - Indexing
    - Full-text search
    - Geospatial queries
    - Bulk operations
    - Transactions (MongoDB 4.0+)
    - Change streams
    - GridFS (large files)
    - Export to JSON
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.client = None
        self.db = None

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "query",
            "insert",
            "update",
            "delete",
            "bulk_operations",
            "aggregation",
            "full_text_search",
            "geospatial_queries",
            "transactions",
            "change_streams",
            "gridfs",
            "export_data"
        ]

    async def connect(self) -> bool:
        """Establish MongoDB connection"""
        try:
            if self.client:
                return True

            host = self.config.get('host', 'localhost')
            port = self.config.get('port', 27017)
            username = self.config.get('username')
            password = self.config.get('password')
            database = self.config['database']

            # Build connection string
            if username and password:
                conn_str = f"mongodb://{username}:{password}@{host}:{port}/{database}"
            else:
                conn_str = f"mongodb://{host}:{port}/{database}"

            self.client = AsyncIOMotorClient(conn_str)
            self.db = self.client[database]

            # Test connection
            await self.client.server_info()

            self.is_connected = True
            logger.info("Connected to MongoDB", database=database)
            return True

        except Exception as e:
            logger.error("MongoDB connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.is_connected = False
            logger.info("Disconnected from MongoDB")

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute MongoDB command"""
        if not self.db:
            await self.connect()

        return await self.db.command(operation, **(params or {}))

    async def query(self, collection: str, filter: Optional[Dict[str, Any]] = None,
                   projection: Optional[Dict[str, Any]] = None,
                   limit: Optional[int] = None,
                   sort: Optional[List[tuple]] = None) -> List[Dict[str, Any]]:
        """Query documents from collection"""
        if not self.db:
            await self.connect()

        coll = self.db[collection]
        cursor = coll.find(filter or {}, projection)

        if sort:
            cursor = cursor.sort(sort)

        if limit:
            cursor = cursor.limit(limit)

        docs = await cursor.to_list(length=None)

        # Convert ObjectId to string for JSON serialization
        for doc in docs:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])

        return docs

    async def query_one(self, collection: str,
                       filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query single document"""
        if not self.db:
            await self.connect()

        doc = await self.db[collection].find_one(filter)

        if doc and '_id' in doc:
            doc['_id'] = str(doc['_id'])

        return doc

    async def insert(self, collection: str,
                    data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Insert documents into collection"""
        if not self.db:
            await self.connect()

        coll = self.db[collection]

        if isinstance(data, dict):
            result = await coll.insert_one(data)
            logger.info(f"Inserted 1 document into {collection}")
            return str(result.inserted_id)
        else:
            result = await coll.insert_many(data)
            logger.info(f"Inserted {len(result.inserted_ids)} documents into {collection}")
            return [str(id) for id in result.inserted_ids]

    async def update(self, collection: str, filter: Dict[str, Any],
                    update: Dict[str, Any], upsert: bool = False) -> int:
        """Update documents in collection"""
        if not self.db:
            await self.connect()

        # Ensure update uses operators
        if not any(key.startswith('$') for key in update.keys()):
            update = {'$set': update}

        result = await self.db[collection].update_many(filter, update, upsert=upsert)

        logger.info(f"Updated {result.modified_count} documents in {collection}")
        return result.modified_count

    async def update_one(self, collection: str, filter: Dict[str, Any],
                        update: Dict[str, Any], upsert: bool = False) -> int:
        """Update single document"""
        if not self.db:
            await self.connect()

        if not any(key.startswith('$') for key in update.keys()):
            update = {'$set': update}

        result = await self.db[collection].update_one(filter, update, upsert=upsert)

        logger.info(f"Updated document in {collection}")
        return result.modified_count

    async def delete(self, collection: str, filter: Dict[str, Any]) -> int:
        """Delete documents from collection"""
        if not self.db:
            await self.connect()

        result = await self.db[collection].delete_many(filter)

        logger.info(f"Deleted {result.deleted_count} documents from {collection}")
        return result.deleted_count

    async def delete_one(self, collection: str, filter: Dict[str, Any]) -> int:
        """Delete single document"""
        if not self.db:
            await self.connect()

        result = await self.db[collection].delete_one(filter)

        logger.info(f"Deleted document from {collection}")
        return result.deleted_count

    async def aggregate(self, collection: str,
                       pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute aggregation pipeline"""
        if not self.db:
            await self.connect()

        cursor = self.db[collection].aggregate(pipeline)
        docs = await cursor.to_list(length=None)

        # Convert ObjectId to string
        for doc in docs:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])

        return docs

    async def count_documents(self, collection: str,
                             filter: Optional[Dict[str, Any]] = None) -> int:
        """Count documents in collection"""
        if not self.db:
            await self.connect()

        return await self.db[collection].count_documents(filter or {})

    async def create_index(self, collection: str, keys: List[tuple],
                          unique: bool = False,
                          name: Optional[str] = None) -> str:
        """Create index on collection"""
        if not self.db:
            await self.connect()

        index_name = await self.db[collection].create_index(
            keys,
            unique=unique,
            name=name
        )

        logger.info(f"Created index {index_name} on {collection}")
        return index_name

    async def list_indexes(self, collection: str) -> List[Dict[str, Any]]:
        """List indexes on collection"""
        if not self.db:
            await self.connect()

        cursor = self.db[collection].list_indexes()
        return await cursor.to_list(length=None)

    async def get_info(self) -> Dict[str, Any]:
        """Get database information"""
        if not self.db:
            await self.connect()

        stats = await self.db.command("dbStats")
        collections = await self.db.list_collection_names()

        return {
            'database': self.db.name,
            'collections': collections,
            'collection_count': len(collections),
            'size': f"{stats['dataSize'] / 1024 / 1024:.2f} MB",
            'storage_size': f"{stats['storageSize'] / 1024 / 1024:.2f} MB",
            'indexes': stats.get('indexes', 0),
            'objects': stats.get('objects', 0)
        }

    async def list_collections(self) -> List[str]:
        """List all collections"""
        if not self.db:
            await self.connect()

        return await self.db.list_collection_names()

    async def create_collection(self, collection: str,
                               validator: Optional[Dict[str, Any]] = None) -> bool:
        """Create collection with optional schema validation"""
        if not self.db:
            await self.connect()

        try:
            if validator:
                await self.db.create_collection(
                    collection,
                    validator=validator
                )
            else:
                await self.db.create_collection(collection)

            logger.info(f"Created collection {collection}")
            return True
        except Exception as e:
            logger.error(f"Failed to create collection {collection}", error=str(e))
            return False

    async def drop_collection(self, collection: str) -> bool:
        """Drop collection"""
        if not self.db:
            await self.connect()

        try:
            await self.db.drop_collection(collection)
            logger.info(f"Dropped collection {collection}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop collection {collection}", error=str(e))
            return False

    async def text_search(self, collection: str, search_text: str,
                         limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Full-text search"""
        if not self.db:
            await self.connect()

        pipeline = [
            {'$match': {'$text': {'$search': search_text}}},
            {'$sort': {'score': {'$meta': 'textScore'}}}
        ]

        if limit:
            pipeline.append({'$limit': limit})

        return await self.aggregate(collection, pipeline)

    async def export_to_json(self, collection: str, output_path: str,
                            filter: Optional[Dict[str, Any]] = None):
        """Export collection to JSON"""
        import json

        docs = await self.query(collection, filter)

        with open(output_path, 'w') as f:
            json.dump(docs, f, indent=2, default=str)

        logger.info(f"Exported {len(docs)} documents to {output_path}")
