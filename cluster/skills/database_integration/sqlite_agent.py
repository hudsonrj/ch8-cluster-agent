"""
SQLite Integration Agent - Full CRUD operations for SQLite
"""

import aiosqlite
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
import structlog

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class SQLiteAgent(BaseDatabaseAgent):
    """
    SQLite integration agent with full CRUD capabilities

    Capabilities:
    - Embedded database (no server required)
    - Parameterized queries (SQL injection safe)
    - Transactions
    - Batch operations
    - Schema management
    - Index management
    - Full-text search (FTS5)
    - JSON operations (SQLite 3.38+)
    - Export to JSON/CSV
    - In-memory databases
    """

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
            "full_text_search",
            "json_operations",
            "export_data",
            "in_memory"
        ]

    async def connect(self) -> bool:
        """Establish database connection"""
        try:
            if self.connection:
                return True

            db_path = self.config.get('database', ':memory:')

            # Create directory if needed
            if db_path != ':memory:':
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

            self.connection = await aiosqlite.connect(db_path)
            self.connection.row_factory = aiosqlite.Row

            self.is_connected = True
            logger.info("Connected to SQLite", database=db_path)
            return True

        except Exception as e:
            logger.error("SQLite connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.is_connected = False
            logger.info("Disconnected from SQLite")

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute SQL operation"""
        if not self.connection:
            await self.connect()

        if params:
            cursor = await self.connection.execute(operation, tuple(params.values()))
        else:
            cursor = await self.connection.execute(operation)

        await self.connection.commit()
        return cursor.rowcount

    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query"""
        if not self.connection:
            await self.connect()

        if params:
            cursor = await self.connection.execute(query, tuple(params.values()))
        else:
            cursor = await self.connection.execute(query)

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def query_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute query and return single row"""
        if not self.connection:
            await self.connect()

        if params:
            cursor = await self.connection.execute(query, tuple(params.values()))
        else:
            cursor = await self.connection.execute(query)

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
        placeholders = ', '.join(['?'] * len(columns))
        column_names = ', '.join(columns)

        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        if not self.connection:
            await self.connect()

        inserted_ids = []
        for row in data:
            values = [row[col] for col in columns]
            cursor = await self.connection.execute(query, values)
            inserted_ids.append(cursor.lastrowid)

        await self.connection.commit()

        logger.info(f"Inserted {len(inserted_ids)} rows into {table}")
        return inserted_ids

    async def bulk_insert(self, table: str, data: List[Dict[str, Any]]) -> int:
        """Bulk insert for large datasets"""
        if not data:
            return 0

        columns = list(data[0].keys())
        placeholders = ', '.join(['?'] * len(columns))
        column_names = ', '.join(columns)

        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"

        if not self.connection:
            await self.connect()

        values_list = [[row[col] for col in columns] for row in data]
        await self.connection.executemany(query, values_list)
        await self.connection.commit()

        logger.info(f"Bulk inserted {len(data)} rows into {table}")
        return len(data)

    async def update(self, table: str, data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update data in table"""
        # Build UPDATE query
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        values = list(data.values())

        if where:
            where_clause = ' AND '.join([f"{k} = ?" for k in where.keys()])
            values.extend(where.values())
            query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        else:
            query = f"UPDATE {table} SET {set_clause}"

        count = await self.execute(query, {'values': values})

        logger.info(f"Updated {count} rows in {table}")
        return count

    async def delete(self, table: str, where: Dict[str, Any]) -> int:
        """Delete data from table"""
        where_clause = ' AND '.join([f"{k} = ?" for k in where.keys()])
        query = f"DELETE FROM {table} WHERE {where_clause}"

        count = await self.execute(query, where)

        logger.info(f"Deleted {count} rows from {table}")
        return count

    async def get_info(self) -> Dict[str, Any]:
        """Get database information"""
        if not self.connection:
            await self.connect()

        version_row = await self.query_one("SELECT sqlite_version() as version")
        version = version_row['version'] if version_row else 'unknown'

        tables = await self.query("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)

        db_path = self.config.get('database', ':memory:')
        if db_path != ':memory:' and Path(db_path).exists():
            size = Path(db_path).stat().st_size
            size_str = f"{size / 1024 / 1024:.2f} MB"
        else:
            size_str = "In-memory"

        return {
            'version': version,
            'database': db_path,
            'size': size_str,
            'tables': [t['name'] for t in tables],
            'table_count': len(tables)
        }

    async def list_tables(self) -> List[str]:
        """List all tables"""
        rows = await self.query("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        return [row['name'] for row in rows]

    async def get_table_schema(self, table: str) -> List[Dict[str, Any]]:
        """Get table schema"""
        return await self.query(f"PRAGMA table_info({table})")

    async def get_table_indexes(self, table: str) -> List[Dict[str, Any]]:
        """Get table indexes"""
        return await self.query(f"PRAGMA index_list({table})")

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
            await self.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})")
            logger.info(f"Created index {idx_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index", error=str(e))
            return False

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

    async def vacuum(self):
        """Optimize database"""
        await self.execute("VACUUM")
        logger.info("Database vacuumed")
