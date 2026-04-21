"""
SQL Extractor Agent - Specialized in SQL database extraction
"""

import asyncpg
import aiomysql
from typing import Dict, Any, List, Optional, Union
import structlog

from .base_extractor import BaseExtractorAgent

logger = structlog.get_logger()


class SQLExtractorAgent(BaseExtractorAgent):
    """
    Specialized agent for SQL database extraction

    Capabilities:
    - Execute SELECT queries
    - Extract table schemas
    - List tables and columns
    - Export to JSON/CSV
    - Parameterized queries
    - Connection pooling
    - Multiple DB support (PostgreSQL, MySQL)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.connection = None
        self.db_type = self.config.get('db_type', 'postgresql')

    def _define_capabilities(self) -> List[str]:
        return [
            "execute_query",
            "extract_table",
            "list_tables",
            "get_schema",
            "export_csv",
            "export_json",
            "parameterized_query"
        ]

    def _get_supported_formats(self) -> List[str]:
        return ["postgresql", "mysql", "sqlite"]

    async def validate(self, source: Any) -> bool:
        """Validate if can connect to database"""
        try:
            await self.connect()
            return True
        except Exception as e:
            logger.error("SQL validation failed", error=str(e))
            return False

    async def connect(self):
        """Establish database connection"""
        if self.connection:
            return

        if self.db_type == 'postgresql':
            self.connection = await asyncpg.connect(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 5432),
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database']
            )
        elif self.db_type == 'mysql':
            self.connection = await aiomysql.connect(
                host=self.config.get('host', 'localhost'),
                port=self.config.get('port', 3306),
                user=self.config['user'],
                password=self.config['password'],
                db=self.config['database']
            )

        logger.info(f"Connected to {self.db_type} database")

    async def disconnect(self):
        """Close database connection"""
        if self.connection:
            if self.db_type == 'postgresql':
                await self.connection.close()
            elif self.db_type == 'mysql':
                self.connection.close()
                await self.connection.wait_closed()

            self.connection = None
            logger.info("Disconnected from database")

    async def extract(self, source: str,
                     query: Optional[Dict[str, Any]] = None) -> Any:
        """
        Extract data from SQL database

        Args:
            source: SQL query string
            query: {
                'params': [value1, value2],  # Query parameters
                'output_format': 'dict' | 'list' | 'dataframe'
            }

        Returns:
            Query results
        """
        query = query or {}

        await self.connect()

        params = query.get('params', [])
        output_format = query.get('output_format', 'dict')

        # Execute query
        if self.db_type == 'postgresql':
            results = await self.connection.fetch(source, *params)

            # Convert to desired format
            if output_format == 'dict':
                return [dict(record) for record in results]
            elif output_format == 'list':
                return [list(record.values()) for record in results]

        elif self.db_type == 'mysql':
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(source, params)
                results = await cursor.fetchall()

                if output_format == 'dict':
                    return results
                elif output_format == 'list':
                    return [list(row.values()) for row in results]

        return results

    async def execute_query(self, sql: str,
                           params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Execute SQL query"""
        return await self.extract(sql, {
            'params': params or [],
            'output_format': 'dict'
        })

    async def extract_table(self, table_name: str,
                           limit: Optional[int] = None,
                           where: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract all data from table"""
        sql = f"SELECT * FROM {table_name}"

        if where:
            sql += f" WHERE {where}"

        if limit:
            sql += f" LIMIT {limit}"

        return await self.execute_query(sql)

    async def list_tables(self) -> List[str]:
        """List all tables in database"""
        await self.connect()

        if self.db_type == 'postgresql':
            results = await self.connection.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            return [row['table_name'] for row in results]

        elif self.db_type == 'mysql':
            async with self.connection.cursor() as cursor:
                await cursor.execute("SHOW TABLES")
                results = await cursor.fetchall()
                return [row[0] for row in results]

        return []

    async def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table schema"""
        await self.connect()

        if self.db_type == 'postgresql':
            results = await self.connection.fetch("""
                SELECT column_name, data_type, character_maximum_length,
                       is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = $1
                ORDER BY ordinal_position
            """, table_name)

            return [dict(row) for row in results]

        elif self.db_type == 'mysql':
            async with self.connection.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(f"DESCRIBE {table_name}")
                results = await cursor.fetchall()
                return results

        return []

    async def get_row_count(self, table_name: str) -> int:
        """Get number of rows in table"""
        result = await self.execute_query(
            f"SELECT COUNT(*) as count FROM {table_name}"
        )
        return result[0]['count']

    async def export_to_json(self, sql: str,
                            output_path: str,
                            params: Optional[List] = None):
        """Export query results to JSON"""
        import json

        data = await self.execute_query(sql, params)

        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Exported {len(data)} rows to {output_path}")

    async def export_to_csv(self, sql: str,
                           output_path: str,
                           params: Optional[List] = None):
        """Export query results to CSV"""
        import csv

        data = await self.execute_query(sql, params)

        if not data:
            logger.warning("No data to export")
            return

        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)

        logger.info(f"Exported {len(data)} rows to {output_path}")
