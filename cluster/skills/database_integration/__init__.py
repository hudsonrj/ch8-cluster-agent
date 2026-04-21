"""
Database Integration Skills - Pre-built specialized agents
for database operations (SQL, NoSQL) and object storage
"""

# SQL Database Integrations
from .postgresql_agent import PostgreSQLAgent
from .mysql_agent import MySQLAgent
from .sqlite_agent import SQLiteAgent
from .sqlserver_agent import SQLServerAgent

# NoSQL Database Integrations
from .mongodb_agent import MongoDBAgent
from .redis_agent import RedisAgent
from .cassandra_agent import CassandraAgent
from .elasticsearch_agent import ElasticsearchAgent
from .dynamodb_agent import DynamoDBAgent

# Object Storage Integrations
from .minio_agent import MinIOAgent
from .s3_agent import S3Agent
from .gcs_agent import GoogleCloudStorageAgent
from .azure_blob_agent import AzureBlobAgent

__all__ = [
    # SQL
    'PostgreSQLAgent',
    'MySQLAgent',
    'SQLiteAgent',
    'SQLServerAgent',
    # NoSQL
    'MongoDBAgent',
    'RedisAgent',
    'CassandraAgent',
    'ElasticsearchAgent',
    'DynamoDBAgent',
    # Object Storage
    'MinIOAgent',
    'S3Agent',
    'GoogleCloudStorageAgent',
    'AzureBlobAgent'
]
