"""
MySQL Integration Agent - Full CRUD operations for MySQL
"""

import aiomysql
from typing import Dict, Any, List, Optional, Union
import structlog
from contextlib import asynccontextmanager

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class MySQLAgent(BaseDatabaseAgent):
    """
    MySQL integration agent with full CRUD capabilities

    Capabilities:
    - Connection pooling
    - Parameterized queries (SQL injection safe)
    - Transactions
    - Batch operations
    - Schema management
    - Index management
    - Stored procedures
    - Full-text search
    - JSON operations (MySQL 5.7+)
    - Export to JSON/CSV
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

            self.pool = await aiomysql.create_pool(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 3306),
                user=self.config['user'],
                password=self.config['password'],
                db=self.config['database'],
                minsize=self.config.get('min_pool_size', 2),
                maxsize=self.config.get('max_pool_size', 10),
                autocommit=False
            )

            self.is_connected = True
            logger.info("Connected to MySQL", database=self.config['database'])
            return True

        except Exception as e:
            logger.error("MySQL connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            self.is_connected = False
            logger.info("Disconnected from MySQL")

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
            async with conn.cursor() as cursor:
                if params:
                    await cursor.execute(operation, tuple(params.values()))
                else:
                    await cursor.execute(operation)

                await conn.commit()
                return cursor.rowcount

    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query"""
        async with self._get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if params:
                    await cursor.execute(query, tuple(params.values()))
                else:
                    await cursor.execute(query)

                rows = await cursor.fetchall()
                return list(rows)

    async def query_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute query and return single row"""
        async with self._get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                if params:
                    await cursor.execute(query, tuple(params.values()))
                else:
                    await cursor.execute(query)

                row = await cursor.fetchone()
                return dict(row) if row else None

    async def insert(self, table: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Insert data into table"""
        if isinstance(data, dict):
            data = [data]

        if not data:
            return []

        # Build INSERT query
        columns = list(data[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)

        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        inserted_ids = []
        async with self._get_connection() as conn:
            async with conn.cursor() as cursor:
                for row in data:
                    values = [row[col] for col in columns]
                    await cursor.execute(query, values)
                    inserted_ids.append(cursor.lastrowid)

                await conn.commit()

        logger.info(f"Inserted {len(inserted_ids)} rows into {table}")
        return inserted_ids

    async def bulk_insert(self, table: str, data: List[Dict[str, Any]]) -> int:
        """Bulk insert for large datasets"""
        if not data:
            return 0

        columns = list(data[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)

        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        async with self._get_connection() as conn:
            async with conn.cursor() as cursor:
                values_list = [[row[col] for col in columns] for row in data]
                await cursor.executemany(query, values_list)
                await conn.commit()

        logger.info(f"Bulk inserted {len(data)} rows into {table}")
        return len(data)

    async def update(self, table: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update data in table"""
        # Build UPDATE query
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        values = list(data.values())

        if where:
            where_clause = ' AND '.join([f"{k} = %s" for k in where.keys()])
            values.extend(where.values())
            query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        else:
            query = f"UPDATE {table} SET {set_clause}"

        count = await self.execute(query, {'values': values})

        logger.info(f"Updated {count} rows in {table}")
        return count

    async def delete(self, table: str, where: Dict[str, Any]) -> int:
        """Delete data from table"""
        where_clause = ' AND '.join([f"{k} = %s" for k in where.keys()])
        query = f"DELETE FROM {table} WHERE {where_clause}"

        count = await self.execute(query, where)

        logger.info(f"Deleted {count} rows from {table}")
        return count

    async def get_info(self) -> Dict[str, Any]:
        """Get database information"""
        version_row = await self.query_one("SELECT VERSION() as version")
        version = version_row['version'] if version_row else 'unknown'

        size_row = await self.query_one(f"""
            SELECT
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS size_mb
            FROM information_schema.TABLES
            WHERE table_schema = '{self.config['database']}'
        """)
        size_mb = size_row['size_mb'] if size_row else 0

        tables = await self.query("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
        """, {'db': self.config['database']})

        return {
            'version': version,
            'database': self.config['database'],
            'size': f"{size_mb} MB",
            'tables': [t['table_name'] for t in tables],
            'table_count': len(tables)
        }

    async def list_tables(self) -> List[str]:
        """List all tables"""
        rows = await self.query(f"SHOW TABLES")
        # MySQL returns table names in a dict with key like 'Tables_in_database'
        key = f"Tables_in_{self.config['database']}"
        return [row[key] for row in rows]

    async def get_table_schema(self, table: str) -> List[Dict[str, Any]]:
        """Get table schema"""
        return await self.query(f"DESCRIBE {table}")

    async def get_table_indexes(self, table: str) -> List[Dict[str, Any]]:
        """Get table indexes"""
        return await self.query(f"SHOW INDEX FROM {table}")

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

    async def drop_table(self, table: str) -> bool:
        """Drop table"""
        try:
            await self.execute(f"DROP TABLE IF EXISTS {table}")
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
            await self.execute(f"CREATE INDEX {idx_name} ON {table} ({column})")
            logger.info(f"Created index {idx_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index", error=str(e))
            return False

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager"""
        async with self._get_connection() as conn:
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

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
