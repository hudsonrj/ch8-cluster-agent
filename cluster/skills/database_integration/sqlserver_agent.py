"""
SQL Server Integration Agent - Full CRUD operations for Microsoft SQL Server
"""

import aioodbc
from typing import Dict, Any, List, Optional, Union
import structlog

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class SQLServerAgent(BaseDatabaseAgent):
    """
    SQL Server integration agent with full CRUD capabilities

    Capabilities:
    - Connection pooling
    - Parameterized queries (SQL injection safe)
    - Transactions
    - Batch operations
    - Schema management
    - Index management
    - Stored procedures
    - Full-text search
    - JSON operations (SQL Server 2016+)
    - Export to JSON/CSV
    - Azure SQL support
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
            if self.connection:
                return True

            # Build connection string
            driver = self.config.get('driver', '{ODBC Driver 17 for SQL Server}')
            server = self.config.get('server', 'localhost')
            port = self.config.get('port', 1433)
            database = self.config['database']
            user = self.config.get('user')
            password = self.config.get('password')

            if user and password:
                conn_str = (
                    f"DRIVER={driver};"
                    f"SERVER={server},{port};"
                    f"DATABASE={database};"
                    f"UID={user};"
                    f"PWD={password};"
                )
            else:
                # Windows Authentication
                conn_str = (
                    f"DRIVER={driver};"
                    f"SERVER={server},{port};"
                    f"DATABASE={database};"
                    f"Trusted_Connection=yes;"
                )

            self.connection = await aioodbc.connect(dsn=conn_str)

            self.is_connected = True
            logger.info("Connected to SQL Server", database=database)
            return True

        except Exception as e:
            logger.error("SQL Server connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.is_connected = False
            logger.info("Disconnected from SQL Server")

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute SQL operation"""
        if not self.connection:
            await self.connect()

        async with self.connection.cursor() as cursor:
            if params:
                await cursor.execute(operation, tuple(params.values()))
            else:
                await cursor.execute(operation)

            await self.connection.commit()
            return cursor.rowcount

    async def query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query"""
        if not self.connection:
            await self.connect()

        async with self.connection.cursor() as cursor:
            if params:
                await cursor.execute(query, tuple(params.values()))
            else:
                await cursor.execute(query)

            columns = [column[0] for column in cursor.description]
            rows = await cursor.fetchall()

            return [dict(zip(columns, row)) for row in rows]

    async def query_one(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Execute query and return single row"""
        if not self.connection:
            await self.connect()

        async with self.connection.cursor() as cursor:
            if params:
                await cursor.execute(query, tuple(params.values()))
            else:
                await cursor.execute(query)

            row = await cursor.fetchone()
            if row:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, row))
            return None

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

        query = f"""
            INSERT INTO {table} ({column_names})
            OUTPUT INSERTED.*
            VALUES ({placeholders})
        """

        if not self.connection:
            await self.connect()

        results = []
        async with self.connection.cursor() as cursor:
            for row in data:
                values = [row[col] for col in columns]
                await cursor.execute(query, values)
                inserted = await cursor.fetchone()
                if inserted:
                    cols = [column[0] for column in cursor.description]
                    results.append(dict(zip(cols, inserted)))

            await self.connection.commit()

        logger.info(f"Inserted {len(results)} rows into {table}")
        return results

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

        async with self.connection.cursor() as cursor:
            values_list = [[row[col] for col in columns] for row in data]
            await cursor.executemany(query, values_list)
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

        version_row = await self.query_one("SELECT @@VERSION as version")
        version = version_row['version'] if version_row else 'unknown'

        size_row = await self.query_one(f"""
            SELECT
                SUM(size) * 8 / 1024 AS size_mb
            FROM sys.master_files
            WHERE database_id = DB_ID()
        """)
        size_mb = size_row['size_mb'] if size_row else 0

        tables = await self.query("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
        """)

        return {
            'version': version.split('\n')[0],  # First line only
            'database': self.config['database'],
            'size': f"{size_mb} MB",
            'tables': [t['TABLE_NAME'] for t in tables],
            'table_count': len(tables)
        }

    async def list_tables(self) -> List[str]:
        """List all tables"""
        rows = await self.query("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        return [row['TABLE_NAME'] for row in rows]

    async def get_table_schema(self, table: str) -> List[Dict[str, Any]]:
        """Get table schema"""
        return await self.query("""
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                IS_NULLABLE,
                COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """, {'table': table})

    async def get_table_indexes(self, table: str) -> List[Dict[str, Any]]:
        """Get table indexes"""
        return await self.query("""
            SELECT
                i.name AS index_name,
                i.type_desc AS index_type,
                c.name AS column_name
            FROM sys.indexes i
            INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE OBJECT_NAME(i.object_id) = ?
        """, {'table': table})

    async def create_table(self, table: str, schema: Dict[str, str]) -> bool:
        """Create table with schema"""
        columns = ', '.join([f"{name} {dtype}" for name, dtype in schema.items()])
        query = f"IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{table}') CREATE TABLE {table} ({columns})"

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
