"""
Elasticsearch Integration Agent - Full operations for Elasticsearch
"""

from elasticsearch import AsyncElasticsearch
from typing import Dict, Any, List, Optional, Union
import structlog

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class ElasticsearchAgent(BaseDatabaseAgent):
    """
    Elasticsearch integration agent with full capabilities

    Capabilities:
    - Document indexing (CRUD)
    - Full-text search
    - Query DSL
    - Aggregations
    - Bulk operations
    - Index management
    - Mapping management
    - Analyzers
    - Filters
    - Export to JSON
    """

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "index_document",
            "search",
            "query_dsl",
            "aggregations",
            "bulk_operations",
            "index_management",
            "mapping_management",
            "analyzers",
            "filters",
            "export_data"
        ]

    async def connect(self) -> bool:
        """Establish Elasticsearch connection"""
        try:
            if self.connection:
                return True

            hosts = self.config.get('hosts', ['localhost:9200'])
            username = self.config.get('username')
            password = self.config.get('password')
            api_key = self.config.get('api_key')

            if api_key:
                self.connection = AsyncElasticsearch(
                    hosts=hosts,
                    api_key=api_key
                )
            elif username and password:
                self.connection = AsyncElasticsearch(
                    hosts=hosts,
                    basic_auth=(username, password)
                )
            else:
                self.connection = AsyncElasticsearch(hosts=hosts)

            # Test connection
            info = await self.connection.info()

            self.is_connected = True
            logger.info("Connected to Elasticsearch", version=info['version']['number'])
            return True

        except Exception as e:
            logger.error("Elasticsearch connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close Elasticsearch connection"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.is_connected = False
            logger.info("Disconnected from Elasticsearch")

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute Elasticsearch operation"""
        if not self.connection:
            await self.connect()

        # Map operation to method
        method = getattr(self.connection, operation, None)
        if not method:
            raise ValueError(f"Unknown operation: {operation}")

        return await method(**(params or {}))

    async def query(self, index: str, query: Dict[str, Any],
                   size: int = 100) -> List[Dict[str, Any]]:
        """Search documents"""
        if not self.connection:
            await self.connect()

        result = await self.connection.search(
            index=index,
            body={'query': query, 'size': size}
        )

        return [hit['_source'] for hit in result['hits']['hits']]

    async def search(self, index: str, query: Dict[str, Any],
                    size: int = 100,
                    sort: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Advanced search with full response"""
        if not self.connection:
            await self.connect()

        body = {'query': query, 'size': size}
        if sort:
            body['sort'] = sort

        return await self.connection.search(index=index, body=body)

    async def insert(self, index: str,
                    data: Union[Dict[str, Any], List[Dict[str, Any]]],
                    doc_id: Optional[str] = None) -> Any:
        """Index document(s)"""
        if not self.connection:
            await self.connect()

        if isinstance(data, dict):
            # Single document
            result = await self.connection.index(
                index=index,
                id=doc_id,
                document=data
            )
            logger.info(f"Indexed 1 document into {index}")
            return result['_id']
        else:
            # Bulk index
            actions = []
            for doc in data:
                actions.append({'index': {'_index': index}})
                actions.append(doc)

            result = await self.connection.bulk(operations=actions)
            logger.info(f"Bulk indexed {len(data)} documents into {index}")
            return result

    async def update(self, index: str, doc_id: str,
                    data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update document"""
        if not self.connection:
            await self.connect()

        await self.connection.update(
            index=index,
            id=doc_id,
            body={'doc': data}
        )

        logger.info(f"Updated document {doc_id} in {index}")
        return 1

    async def delete(self, index: str, doc_id: Optional[str] = None,
                    query: Optional[Dict[str, Any]] = None) -> int:
        """Delete document(s)"""
        if not self.connection:
            await self.connect()

        if doc_id:
            # Delete single document
            await self.connection.delete(index=index, id=doc_id)
            logger.info(f"Deleted document {doc_id} from {index}")
            return 1
        elif query:
            # Delete by query
            result = await self.connection.delete_by_query(
                index=index,
                body={'query': query}
            )
            logger.info(f"Deleted {result['deleted']} documents from {index}")
            return result['deleted']
        else:
            raise ValueError("Either doc_id or query must be provided")

    async def aggregate(self, index: str,
                       aggregations: Dict[str, Any],
                       query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute aggregation"""
        if not self.connection:
            await self.connect()

        body = {'aggs': aggregations}
        if query:
            body['query'] = query

        result = await self.connection.search(index=index, body=body, size=0)
        return result['aggregations']

    async def create_index(self, index: str,
                          mapping: Optional[Dict[str, Any]] = None,
                          settings: Optional[Dict[str, Any]] = None) -> bool:
        """Create index"""
        if not self.connection:
            await self.connect()

        try:
            body = {}
            if mapping:
                body['mappings'] = mapping
            if settings:
                body['settings'] = settings

            await self.connection.indices.create(index=index, body=body if body else None)
            logger.info(f"Created index {index}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index {index}", error=str(e))
            return False

    async def delete_index(self, index: str) -> bool:
        """Delete index"""
        if not self.connection:
            await self.connect()

        try:
            await self.connection.indices.delete(index=index)
            logger.info(f"Deleted index {index}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete index {index}", error=str(e))
            return False

    async def list_indices(self) -> List[str]:
        """List all indices"""
        if not self.connection:
            await self.connect()

        indices = await self.connection.cat.indices(format='json')
        return [idx['index'] for idx in indices]

    async def get_info(self) -> Dict[str, Any]:
        """Get Elasticsearch information"""
        if not self.connection:
            await self.connect()

        info = await self.connection.info()
        cluster_health = await self.connection.cluster.health()
        indices = await self.list_indices()

        return {
            'version': info['version']['number'],
            'cluster_name': info['cluster_name'],
            'cluster_status': cluster_health['status'],
            'indices': indices,
            'index_count': len(indices),
            'nodes': cluster_health['number_of_nodes']
        }

    async def export_to_json(self, index: str, query: Dict[str, Any],
                            output_path: str, size: int = 10000):
        """Export search results to JSON"""
        import json

        docs = await self.query(index, query, size=size)

        with open(output_path, 'w') as f:
            json.dump(docs, f, indent=2, default=str)

        logger.info(f"Exported {len(docs)} documents to {output_path}")
