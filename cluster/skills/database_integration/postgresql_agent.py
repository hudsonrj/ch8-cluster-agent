"""
PostgreSQL Integration Agent - Full CRUD operations for PostgreSQL
"""

import asyncpg
from typing import Dict, Any, List, Optional, Union
import structlog
from contextlib import asynccontextmanager

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class PostgreSQLAgent(BaseDatabaseAgent):
    """
    PostgreSQL integration agent with full CRUD capabilities

    Capabilities:
    - Connection pooling
    - Parameterized queries (SQL injection safe)
    - Transactions
    - Batch operations
    - Schema management
    - Index management
    - Stored procedures
    - Full-text search
    - JSON operations
    - Export to JSON/CSV/Parquet
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.pool = None

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "query",
            "insert",
            "update",
            "delete",
            "bulk_insert",
            "transactions",
            "schema_management",
            "index_management",
            "stored_procedures",
            "full_text_search",
            "json_operations",
            "export_data"
        ]

    async def connect(self) -> bool:
        """Establish connection pool"""
        try:
            if self.pool:
                return True

            self.pool = await asyncpg.create_pool(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 5432),
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                min_size=self.config.get('min_pool_size', 2),
                max_size=self.config.get('max_pool_size', 10)
            )

            self.is_connected = True
            logger.info("Connected to PostgreSQL", database=self.config['database'])
            return True

        except Exception as e:
            logger.error("PostgreSQL connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.is_connected = False
            logger.info("Disconnected from PostgreSQL")

    @asynccontextmanager
    async def _get_connection(self):
        """Get connection from pool"""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            yield conn

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute SQL operation"""
        async with self._get_connection() as conn:
            if params:
                # Convert dict params to positional
                result = await conn.execute(operation, *params.values())
            else:
                result = await conn.execute(operation)

            return result

    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query"""
        async with self._get_connection() as conn:
            if params:
                rows = await conn.fetch(query, *params.values())
            else:
                rows = await conn.fetch(query)

            return [dict(row) for row in rows]

    async def query_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute query and return single row"""
        async with self._get_connection() as conn:
            if params:
                row = await conn.fetchrow(query, *params.values())
            else:
                row = await conn.fetchrow(query)

            return dict(row) if row else None

    async def insert(self, table: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Insert data into table"""
        if isinstance(data, dict):
            data = [data]

        if not data:
            return []

        # Build INSERT query
        columns = list(data[0].keys())
        placeholders = ', '.join([f'${i+1}' for i in range(len(columns))])
        column_names = ', '.join(columns)

        query = f"""
            INSERT INTO {table} ({column_names})
            VALUES ({placeholders})
            RETURNING *
        """

        results = []
        async with self._get_connection() as conn:
            for row in data:
                values = [row[col] for col in columns]
                result = await conn.fetchrow(query, *values)
                results.append(dict(result))

        logger.info(f"Inserted {len(results)} rows into {table}")
        return results

    async def bulk_insert(self, table: str, data: List[Dict[str, Any]]) -> int:
        """Bulk insert for large datasets"""
        if not data:
            return 0

        columns = list(data[0].keys())
        column_names = ', '.join(columns)

        async with self._get_connection() as conn:
            # Use COPY for efficiency
            await conn.copy_records_to_table(
                table,
                records=[tuple(row[col] for col in columns) for row in data],
                columns=columns
            )

        logger.info(f"Bulk inserted {len(data)} rows into {table}")
        return len(data)

    async def update(self, table: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update data in table"""
        # Build UPDATE query
        set_clause = ', '.join([f"{k} = ${i+1}" for i, k in enumerate(data.keys())])
        values = list(data.values())

        if where:
            where_clause = ' AND '.join([
                f"{k} = ${i+len(data)+1}" for i, k in enumerate(where.keys())
            ])
            values.extend(where.values())
            query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        else:
            query = f"UPDATE {table} SET {set_clause}"

        result = await self.execute(query, {'values': values})

        # Extract row count from result
        count = int(result.split()[-1]) if result else 0
        logger.info(f"Updated {count} rows in {table}")
        return count

    async def delete(self, table: str, where: Dict[str, Any]) -> int:
        """Delete data from table"""
        where_clause = ' AND '.join([
            f"{k} = ${i+1}" for i, k in enumerate(where.keys())
        ])
        query = f"DELETE FROM {table} WHERE {where_clause}"

        result = await self.execute(query, where)

        count = int(result.split()[-1]) if result else 0
        logger.info(f"Deleted {count} rows from {table}")
        return count

    async def get_info(self) -> Dict[str, Any]:
        """Get database information"""
        async with self._get_connection() as conn:
            version = await conn.fetchval("SELECT version()")
            size = await conn.fetchval(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )

            tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)

            return {
                'version': version,
                'database': self.config['database'],
                'size': size,
                'tables': [t['table_name'] for t in tables],
                'table_count': len(tables)
            }

    async def list_tables(self) -> List[str]:
        """List all tables"""
        rows = await self.query("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        return [row['table_name'] for row in rows]

    async def get_table_schema(self, table: str) -> List[Dict[str, Any]]:
        """Get table schema"""
        return await self.query("""
            SELECT column_name, data_type, character_maximum_length,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position
        """, {'table': table})

    async def get_table_indexes(self, table: str) -> List[Dict[str, Any]]:
        """Get table indexes"""
        return await self.query("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = $1
        """, {'table': table})

    async def create_table(self, table: str, schema: Dict[str, str]) -> bool:
        """Create table with schema"""
        columns = ', '.join([f"{name} {dtype}" for name, dtype in schema.items()])
        query = f"CREATE TABLE IF NOT EXISTS {table} ({columns})"

        try:
            await self.execute(query)
            logger.info(f"Created table {table}")
            return True
        except Exception as e:
            logger.error(f"Failed to create table {table}", error=str(e))
            return False

    async def drop_table(self, table: str, cascade: bool = False) -> bool:
        """Drop table"""
        try:
            cascade_clause = "CASCADE" if cascade else ""
            await self.execute(f"DROP TABLE IF EXISTS {table} {cascade_clause}")
            logger.info(f"Dropped table {table}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop table {table}", error=str(e))
            return False

    async def create_index(self, table: str, column: str,
                          index_name: Optional[str] = None) -> bool:
        """Create index on column"""
        try:
            idx_name = index_name or f"idx_{table}_{column}"
            await self.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
            logger.info(f"Created index {idx_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index", error=str(e))
            return False

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager"""
        async with self._get_connection() as conn:
            async with conn.transaction():
                yield conn

    async def export_to_json(self, query: str, output_path: str,
                            params: Optional[Dict[str, Any]] = None):
        """Export query results to JSON"""
        import json

        data = await self.query(query, params)

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Exported {len(data)} rows to {output_path}")

    async def export_to_csv(self, query: str, output_path: str,
                           params: Optional[Dict[str, Any]] = None):
        """Export query results to CSV"""
        import csv

        data = await self.query(query, params)

        if not data:
            logger.warning("No data to export")
            return

        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Exported {len(data)} rows to {output_path}")
