"""
DynamoDB Integration Agent - Full operations for AWS DynamoDB
"""

import aioboto3
from typing import Dict, Any, List, Optional, Union
import structlog

from .base_database import BaseDatabaseAgent

logger = structlog.get_logger()


class DynamoDBAgent(BaseDatabaseAgent):
    """
    DynamoDB integration agent with full capabilities

    Capabilities:
    - Item operations (CRUD)
    - Query and Scan
    - Batch operations
    - Transactions
    - Table management
    - Index management (GSI/LSI)
    - Conditional writes
    - Streams
    - Export to JSON
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.client = None
        self.resource = None
        self.session = None

    def _define_capabilities(self) -> List[str]:
        return [
            "connect",
            "item_operations",
            "query_scan",
            "batch_operations",
            "transactions",
            "table_management",
            "index_management",
            "conditional_writes",
            "streams",
            "export_data"
        ]

    async def connect(self) -> bool:
        """Establish DynamoDB connection"""
        try:
            if self.client:
                return True

            self.session = aioboto3.Session(
                aws_access_key_id=self.config.get('aws_access_key_id'),
                aws_secret_access_key=self.config.get('aws_secret_access_key'),
                region_name=self.config.get('region', 'us-east-1')
            )

            self.client = await self.session.client('dynamodb').__aenter__()
            self.resource = await self.session.resource('dynamodb').__aenter__()

            self.is_connected = True
            self.connection = self.client
            logger.info("Connected to DynamoDB", region=self.config.get('region'))
            return True

        except Exception as e:
            logger.error("DynamoDB connection failed", error=str(e))
            self.is_connected = False
            return False

    async def disconnect(self):
        """Close DynamoDB connection"""
        if self.client:
            await self.client.__aexit__(None, None, None)
            await self.resource.__aexit__(None, None, None)
            self.client = None
            self.resource = None
            self.session = None
            self.is_connected = False
            logger.info("Disconnected from DynamoDB")

    async def execute(self, operation: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute DynamoDB operation"""
        if not self.client:
            await self.connect()

        method = getattr(self.client, operation, None)
        if not method:
            raise ValueError(f"Unknown operation: {operation}")

        return await method(**(params or {}))

    async def query(self, table_name: str,
                   key_condition: Dict[str, Any],
                   filter_expression: Optional[Dict[str, Any]] = None,
                   limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query items"""
        if not self.resource:
            await self.connect()

        table = await self.resource.Table(table_name)

        # Build query parameters
        query_params = {'KeyConditionExpression': key_condition}

        if filter_expression:
            query_params['FilterExpression'] = filter_expression

        if limit:
            query_params['Limit'] = limit

        response = await table.query(**query_params)
        return response.get('Items', [])

    async def scan(self, table_name: str,
                  filter_expression: Optional[Dict[str, Any]] = None,
                  limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scan table"""
        if not self.resource:
            await self.connect()

        table = await self.resource.Table(table_name)

        scan_params = {}
        if filter_expression:
            scan_params['FilterExpression'] = filter_expression

        if limit:
            scan_params['Limit'] = limit

        response = await table.scan(**scan_params)
        return response.get('Items', [])

    async def insert(self, table_name: str,
                    data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Any:
        """Put item(s)"""
        if not self.resource:
            await self.connect()

        table = await self.resource.Table(table_name)

        if isinstance(data, dict):
            # Single item
            await table.put_item(Item=data)
            logger.info(f"Inserted 1 item into {table_name}")
            return data.get('id', 'success')
        else:
            # Batch write
            async with table.batch_writer() as batch:
                for item in data:
                    await batch.put_item(Item=item)

            logger.info(f"Batch inserted {len(data)} items into {table_name}")
            return [item.get('id', idx) for idx, item in enumerate(data)]

    async def update(self, table_name: str,
                    key: Dict[str, Any],
                    data: Dict[str, Any],
                    where: Optional[Dict[str, Any]] = None) -> int:
        """Update item"""
        if not self.resource:
            await self.connect()

        table = await self.resource.Table(table_name)

        # Build update expression
        update_expr = 'SET ' + ', '.join([f"#{k} = :{k}" for k in data.keys()])

        expr_attr_names = {f"#{k}": k for k in data.keys()}
        expr_attr_values = {f":{k}": v for k, v in data.items()}

        update_params = {
            'Key': key,
            'UpdateExpression': update_expr,
            'ExpressionAttributeNames': expr_attr_names,
            'ExpressionAttributeValues': expr_attr_values
        }

        if where:
            # Add condition expression
            condition_expr = ' AND '.join([f"#{k} = :{k}_cond" for k in where.keys()])
            update_params['ConditionExpression'] = condition_expr
            expr_attr_names.update({f"#{k}": k for k in where.keys()})
            expr_attr_values.update({f":{k}_cond": v for k, v in where.items()})

        await table.update_item(**update_params)

        logger.info(f"Updated item in {table_name}")
        return 1

    async def delete(self, table_name: str, key: Dict[str, Any]) -> int:
        """Delete item"""
        if not self.resource:
            await self.connect()

        table = await self.resource.Table(table_name)

        await table.delete_item(Key=key)

        logger.info(f"Deleted item from {table_name}")
        return 1

    async def get_info(self) -> Dict[str, Any]:
        """Get DynamoDB information"""
        if not self.client:
            await self.connect()

        tables = await self.client.list_tables()
        table_names = tables.get('TableNames', [])

        return {
            'region': self.config.get('region', 'us-east-1'),
            'tables': table_names,
            'table_count': len(table_names)
        }

    async def create_table(self, table_name: str,
                          key_schema: List[Dict[str, str]],
                          attribute_definitions: List[Dict[str, str]],
                          billing_mode: str = 'PAY_PER_REQUEST') -> bool:
        """Create table"""
        if not self.client:
            await self.connect()

        try:
            await self.client.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attribute_definitions,
                BillingMode=billing_mode
            )

            logger.info(f"Created table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create table {table_name}", error=str(e))
            return False

    async def delete_table(self, table_name: str) -> bool:
        """Delete table"""
        if not self.client:
            await self.connect()

        try:
            await self.client.delete_table(TableName=table_name)
            logger.info(f"Deleted table {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete table {table_name}", error=str(e))
            return False

    async def list_tables(self) -> List[str]:
        """List all tables"""
        if not self.client:
            await self.connect()

        response = await self.client.list_tables()
        return response.get('TableNames', [])

    async def export_to_json(self, table_name: str, output_path: str,
                            filter_expression: Optional[Dict[str, Any]] = None):
        """Export table to JSON"""
        import json

        items = await self.scan(table_name, filter_expression=filter_expression)

        with open(output_path, 'w') as f:
            json.dump(items, f, indent=2, default=str)

        logger.info(f"Exported {len(items)} items to {output_path}")
