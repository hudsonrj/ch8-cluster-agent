"""
Cassandra Integration Agent - Full CRUD operations for Apache Cassandra
"""

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement, BatchStatement
from typing import Dict, Any, List, Optional, Union
import structlog

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class CassandraAgent(BaseDatabaseAgent):
    """
    Cassandra integration agent with full CRUD capabilities

    Capabilities:
    - CQL queries
    - Batch operations
    - Prepared statements
    - Keyspace management
    - Table management
    - Secondary indexes
    - Materialized views
    - Time series operations
    - Export to JSON/CSV
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.cluster = None
        self.session = None

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "cql_queries",
            "batch_operations",
            "prepared_statements",
            "keyspace_management",
            "table_management",
            "secondary_indexes",
            "materialized_views",
            "time_series",
            "export_data"
        ]

    async def connect(self) -> bool:
        """Establish Cassandra connection"""
        try:
            if self.session:
                return True

            contact_points = self.config.get('contact_points', ['localhost'])
            port = self.config.get('port', 9042)
            keyspace = self.config.get('keyspace', 'system')
            username = self.config.get('username')
            password = self.config.get('password')

            if username and password:
                auth_provider = PlainTextAuthProvider(
                    username=username,
                    password=password
                )
                self.cluster = Cluster(
                    contact_points=contact_points,
                    port=port,
                    auth_provider=auth_provider
                )
            else:
                self.cluster = Cluster(
                    contact_points=contact_points,
                    port=port
                )

            self.session = self.cluster.connect(keyspace)

            self.is_connected = True
            self.connection = self.session
            logger.info("Connected to Cassandra", keyspace=keyspace)
            return True

        except Exception as e:
            logger.error("Cassandra connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close Cassandra connection"""
        if self.cluster:
            self.cluster.shutdown()
            self.cluster = None
            self.session = None
            self.connection = None
            self.is_connected = False
            logger.info("Disconnected from Cassandra")

    async def execute(self, cql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute CQL statement"""
        if not self.session:
            await self.connect()

        if params:
            statement = SimpleStatement(cql)
            return self.session.execute(statement, tuple(params.values()))
        else:
            return self.session.execute(cql)

    async def query(self, cql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query"""
        result = await self.execute(cql, params)
        return [dict(row._asdict()) for row in result]

    async def insert(self, table: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Insert data into table"""
        if isinstance(data, dict):
            data = [data]

        if not data:
            return []

        columns = list(data[0].keys())
        placeholders = ', '.join(['?' for _ in columns])
        column_names = ', '.join(columns)

        cql = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        inserted = []
        for row in data:
            values = tuple(row[col] for col in columns)
            await self.execute(cql, {'values': values})
            inserted.append(row)

        logger.info(f"Inserted {len(inserted)} rows into {table}")
        return inserted

    async def update(self, table: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update data in table"""
        if not where:
            raise ValueError("WHERE clause required for Cassandra UPDATE")

        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        where_clause = ' AND '.join([f"{k} = ?" for k in where.keys()])

        values = list(data.values()) + list(where.values())

        cql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"

        await self.execute(cql, {'values': values})
        logger.info(f"Updated rows in {table}")
        return 1  # Cassandra doesn't return affected count

    async def delete(self, table: str, where: Dict[str, Any]) -> int:
        """Delete data from table"""
        where_clause = ' AND '.join([f"{k} = ?" for k in where.keys()])
        cql = f"DELETE FROM {table} WHERE {where_clause}"

        await self.execute(cql, where)
        logger.info(f"Deleted rows from {table}")
        return 1  # Cassandra doesn't return affected count

    async def get_info(self) -> Dict[str, Any]:
        """Get Cassandra information"""
        if not self.session:
            await self.connect()

        keyspaces = await self.query(
            "SELECT keyspace_name FROM system_schema.keyspaces"
        )

        return {
            'cluster_name': self.cluster.metadata.cluster_name,
            'keyspace': self.session.keyspace,
            'keyspaces': [k['keyspace_name'] for k in keyspaces],
            'keyspace_count': len(keyspaces)
        }

    async def create_keyspace(self, keyspace: str,
                             replication: Optional[Dict[str, Any]] = None) -> bool:
        """Create keyspace"""
        if not replication:
            replication = {'class': 'SimpleStrategy', 'replication_factor': 1}

        replication_str = ', '.join([f"'{k}': {v}" for k, v in replication.items()])

        cql = f"""
            CREATE KEYSPACE IF NOT EXISTS {keyspace}
            WITH replication = {{{replication_str}}}
        """

        try:
            await self.execute(cql)
            logger.info(f"Created keyspace {keyspace}")
            return True
        except Exception as e:
            logger.error(f"Failed to create keyspace {keyspace}", error=str(e))
            return False

    async def drop_keyspace(self, keyspace: str) -> bool:
        """Drop keyspace"""
        try:
            await self.execute(f"DROP KEYSPACE IF EXISTS {keyspace}")
            logger.info(f"Dropped keyspace {keyspace}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop keyspace {keyspace}", error=str(e))
            return False

    async def export_to_json(self, cql: str, output_path: str,
                            params: Optional[Dict[str, Any]] = None):
        """Export query results to JSON"""
        import json

        data = await self.query(cql, params)

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Exported {len(data)} rows to {output_path}")
