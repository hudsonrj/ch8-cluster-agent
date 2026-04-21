# Database & Storage Integration Skills

Comprehensive pre-built agents for database operations (SQL, NoSQL) and object storage integrations.

## 📦 SQL Databases

### PostgreSQL (`PostgreSQLAgent`)
Full-featured PostgreSQL integration with connection pooling and async operations.

```python
from cluster.skills.database_integration import PostgreSQLAgent

# Initialize
agent = PostgreSQLAgent({
    'host': 'localhost',
    'port': 5432,
    'user': 'username',
    'password': 'password',
    'database': 'mydb'
})

# Connect
await agent.connect()

# Query
results = await agent.query("SELECT * FROM users WHERE active = $1", {'active': True})

# Insert
await agent.insert('users', {'name': 'John', 'email': 'john@example.com'})

# Update
await agent.update('users', {'status': 'inactive'}, where={'id': 123})

# Transactions
async with agent.transaction() as conn:
    # Multiple operations in transaction
    pass
```

### MySQL (`MySQLAgent`)
Complete MySQL support with connection pooling.

```python
from cluster.skills.database_integration import MySQLAgent

agent = MySQLAgent({
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'password',
    'database': 'mydb'
})
```

### SQLite (`SQLiteAgent`)
Embedded database support with in-memory option.

```python
from cluster.skills.database_integration import SQLiteAgent

# File-based
agent = SQLiteAgent({'database': '/path/to/database.db'})

# In-memory
agent = SQLiteAgent({'database': ':memory:'})
```

### SQL Server (`SQLServerAgent`)
Microsoft SQL Server integration with Azure SQL support.

```python
from cluster.skills.database_integration import SQLServerAgent

agent = SQLServerAgent({
    'server': 'localhost',
    'port': 1433,
    'database': 'mydb',
    'user': 'sa',
    'password': 'password'
})
```

## 🗄️ NoSQL Databases

### MongoDB (`MongoDBAgent`)
Document database with aggregation pipelines.

```python
from cluster.skills.database_integration import MongoDBAgent

agent = MongoDBAgent({
    'host': 'localhost',
    'port': 27017,
    'database': 'mydb',
    'username': 'user',
    'password': 'pass'
})

# Query documents
docs = await agent.query('users', {'age': {'$gt': 18}})

# Insert
await agent.insert('users', {'name': 'Alice', 'age': 25})

# Aggregation
pipeline = [
    {'$match': {'status': 'active'}},
    {'$group': {'_id': '$category', 'count': {'$sum': 1}}}
]
results = await agent.aggregate('products', pipeline)
```

### Redis (`RedisAgent`)
In-memory data structure store.

```python
from cluster.skills.database_integration import RedisAgent

agent = RedisAgent({
    'host': 'localhost',
    'port': 6379,
    'db': 0
})

# String operations
await agent.set('key', 'value', ex=3600)  # with TTL
value = await agent.get('key')

# Hash operations
await agent.hset('user:123', 'name', 'John')
user = await agent.hgetall('user:123')

# List operations
await agent.rpush('queue', 'task1', 'task2')
items = await agent.lrange('queue', 0, -1)
```

### Cassandra (`CassandraAgent`)
Distributed wide-column store.

```python
from cluster.skills.database_integration import CassandraAgent

agent = CassandraAgent({
    'contact_points': ['localhost'],
    'port': 9042,
    'keyspace': 'mykeyspace'
})

# CQL queries
await agent.query("SELECT * FROM users WHERE user_id = ?", {'user_id': 123})
```

### Elasticsearch (`ElasticsearchAgent`)
Full-text search and analytics engine.

```python
from cluster.skills.database_integration import ElasticsearchAgent

agent = ElasticsearchAgent({
    'hosts': ['localhost:9200'],
    'username': 'elastic',
    'password': 'password'
})

# Index document
await agent.insert('products', {'name': 'Widget', 'price': 29.99})

# Search
results = await agent.search('products', {
    'match': {'name': 'widget'}
})

# Aggregations
aggs = await agent.aggregate('products', {
    'avg_price': {'avg': {'field': 'price'}}
})
```

### DynamoDB (`DynamoDBAgent`)
AWS managed NoSQL database.

```python
from cluster.skills.database_integration import DynamoDBAgent

agent = DynamoDBAgent({
    'aws_access_key_id': 'YOUR_KEY',
    'aws_secret_access_key': 'YOUR_SECRET',
    'region': 'us-east-1'
})

# Query with key condition
items = await agent.query('users', key_condition={'user_id': 123})

# Put item
await agent.insert('users', {'user_id': 123, 'name': 'John'})
```

## ☁️ Object Storage

### MinIO (`MinIOAgent`)
S3-compatible object storage.

```python
from cluster.skills.database_integration import MinIOAgent

agent = MinIOAgent({
    'endpoint': 'localhost:9000',
    'access_key': 'minioadmin',
    'secret_key': 'minioadmin',
    'secure': False
})

# Upload file
await agent.upload('mybucket', 'file.txt', file_path='/path/to/file.txt')

# Upload bytes
await agent.upload('mybucket', 'data.bin', data=b'binary data')

# Download
data = await agent.download('mybucket', 'file.txt')

# List objects
objects = await agent.list_objects('mybucket', prefix='documents/')

# Presigned URL
url = await agent.presigned_get_url('mybucket', 'file.txt', expires_seconds=3600)
```

### AWS S3 (`S3Agent`)
Amazon S3 cloud storage.

```python
from cluster.skills.database_integration import S3Agent

agent = S3Agent({
    'aws_access_key_id': 'YOUR_KEY',
    'aws_secret_access_key': 'YOUR_SECRET',
    'region': 'us-east-1'
})

# Same interface as MinIO
await agent.upload('mybucket', 'file.txt', file_path='/path/to/file.txt')
await agent.download('mybucket', 'file.txt', file_path='/download/path.txt')
```

### Google Cloud Storage (`GoogleCloudStorageAgent`)
GCP object storage.

```python
from cluster.skills.database_integration import GoogleCloudStorageAgent

agent = GoogleCloudStorageAgent({
    'credentials_path': '/path/to/credentials.json',
    'project_id': 'my-project'
})

# Upload/download with same interface
await agent.upload('mybucket', 'file.txt', file_path='/path/to/file.txt')
```

### Azure Blob Storage (`AzureBlobAgent`)
Microsoft Azure blob storage.

```python
from cluster.skills.database_integration import AzureBlobAgent

agent = AzureBlobAgent({
    'connection_string': 'DefaultEndpointsProtocol=https;...'
})

# Upload/download (containers = buckets)
await agent.upload('mycontainer', 'file.txt', file_path='/path/to/file.txt')

# Generate SAS URL
url = await agent.generate_sas_url('mycontainer', 'file.txt', expires_seconds=3600)
```

## 🔧 Common Features

All agents support:

- **Async/await patterns** - Non-blocking operations
- **Connection pooling** - Efficient resource management
- **Error handling** - Structured logging with context
- **Health checks** - `await agent.health_check()`
- **Info retrieval** - `await agent.get_info()`
- **Export capabilities** - JSON/CSV export for data extraction

## 📦 Installation

```bash
# Install all dependencies
pip install -r cluster/skills/database_integration/requirements.txt

# Or install specific groups
pip install asyncpg aiomysql aiosqlite  # SQL only
pip install motor aioredis elasticsearch  # NoSQL only
pip install minio boto3 google-cloud-storage azure-storage-blob  # Storage only
```

## 🏗️ Architecture

All agents inherit from base classes:

- `BaseDatabaseAgent` - Common database interface (SQL & NoSQL)
- `BaseStorageAgent` - Common storage interface (object stores)

This ensures consistent API across all integrations.

## 🚀 Usage in CH8 Agent

These agents can be used as:

1. **Standalone skills** - Direct integration in your code
2. **MCP integration agents** - Connect nodes to external services
3. **Subagents** - Managed by agent nodes for specialized tasks
4. **Data extraction** - Combined with data extraction agents

Example with agent node:

```python
# Register as subagent capability
node.register_subagent('postgresql', PostgreSQLAgent({
    'host': 'db.example.com',
    'database': 'production'
}))

# Use in task execution
result = await node.execute_with_subagent('postgresql', 'query',
    query="SELECT * FROM orders WHERE status = 'pending'"
)
```

## 🔐 Security

- Always use parameterized queries to prevent SQL injection
- Store credentials in environment variables or secure vaults
- Use connection pooling to limit resource usage
- Enable SSL/TLS for production deployments
- Follow principle of least privilege for database users

## 📊 Performance

- Connection pooling is enabled by default
- Batch operations for bulk inserts (10-100x faster)
- Async operations prevent blocking
- Prepared statements for repeated queries
- Predicate pushdown where supported (Parquet, DynamoDB)

## 🧪 Testing

```python
# Health check
status = await agent.health_check()
assert status['healthy'] == True

# Connection test
connected = await agent.connect()
assert connected == True

# Info retrieval
info = await agent.get_info()
print(f"Database: {info['database']}")
```

## 📝 License

Part of the CH8 Agent project.
