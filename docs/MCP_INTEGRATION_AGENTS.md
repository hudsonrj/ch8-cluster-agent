# MCP Integration Agents - CH8 Agent

**Data:** 2026-04-21
**Status:** Proposta de Design

---

## 🎯 Visão Geral

Cada nó do CH8 Agent pode criar **Integration Agents** personalizados via MCP (Model Context Protocol) para conectar com serviços externos:

- 📊 **Bancos de dados** (PostgreSQL, MongoDB, Redis)
- 🌐 **APIs externas** (REST, GraphQL, gRPC)
- 📁 **Sistemas de arquivos** (local, S3, GCS)
- 🧠 **RAG systems** (vector databases, semantic search)
- 🏢 **Sistemas corporativos** (ERP, CRM, LDAP)
- 📨 **Mensageria** (Kafka, RabbitMQ, SQS)
- E qualquer outra integração customizada

---

## 🏗️ Arquitetura de Integration Agents

### Conceito

```
┌───────────────────────────────────────────────┐
│              CH8 Agent Node                   │
│                                               │
│  ┌──────────────────────────────────────┐    │
│  │  Main Agent                          │    │
│  │  (Decision making, task coordination)│    │
│  └─────────────┬────────────────────────┘    │
│                │                              │
│    ┌───────────┴───────────┐                 │
│    │                       │                 │
│    ▼                       ▼                 │
│  ┌─────────────┐    ┌─────────────┐         │
│  │ SubAgent 1  │    │ SubAgent 2  │         │
│  │ (task exec) │    │ (analysis)  │         │
│  └─────────────┘    └─────────────┘         │
│                                               │
│  ┌───────────────────────────────────────┐   │
│  │    Integration Agents (MCP)           │   │
│  │                                       │   │
│  │  ┌──────┐  ┌──────┐  ┌──────┐       │   │
│  │  │ DB   │  │ API  │  │ RAG  │  ...  │   │
│  │  │Agent │  │Agent │  │Agent │       │   │
│  │  └───┬──┘  └───┬──┘  └───┬──┘       │   │
│  └──────┼─────────┼─────────┼───────────┘   │
└─────────┼─────────┼─────────┼───────────────┘
          │         │         │
          ▼         ▼         ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │   DB    │ │   API   │ │   RAG   │
    │ Server  │ │ Service │ │ System  │
    └─────────┘ └─────────┘ └─────────┘
```

### Características

1. **Integration Agents são especializados** em um tipo de serviço
2. **Cada nó pode ter seus próprios** Integration Agents
3. **MCP define protocolo padrão** de comunicação
4. **Plugins dinâmicos** - adicione novos sem restart
5. **Compartilháveis** - nós podem usar Integration Agents de outros nós

---

## 📝 MCP Integration Agent Interface

### Base Interface

```python
# cluster/integration/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List

class MCPIntegrationAgent(ABC):
    """
    Base class for all MCP Integration Agents
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agent_id = config['agent_id']
        self.service_type = config['service_type']
        self.capabilities = self._define_capabilities()

    @abstractmethod
    def _define_capabilities(self) -> List[str]:
        """Define what this agent can do"""
        pass

    @abstractmethod
    async def connect(self):
        """Establish connection to external service"""
        pass

    @abstractmethod
    async def disconnect(self):
        """Close connection"""
        pass

    @abstractmethod
    async def execute_action(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute an action on the external service"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if service is available"""
        pass

    async def get_capabilities(self) -> Dict[str, Any]:
        """Return agent capabilities in MCP format"""
        return {
            'agent_id': self.agent_id,
            'service_type': self.service_type,
            'capabilities': self.capabilities,
            'mcp_version': '1.0',
            'actions': self._list_actions()
        }

    @abstractmethod
    def _list_actions(self) -> List[Dict[str, Any]]:
        """List all available actions"""
        pass
```

---

## 🗄️ Exemplo: Database Integration Agent

```python
# cluster/integration/database_agent.py

class DatabaseIntegrationAgent(MCPIntegrationAgent):
    """
    MCP Integration Agent for databases
    Supports: PostgreSQL, MySQL, MongoDB, Redis
    """

    def _define_capabilities(self):
        return [
            "query_data",
            "insert_data",
            "update_data",
            "delete_data",
            "execute_transaction",
            "schema_introspection"
        ]

    async def connect(self):
        """Connect to database"""
        db_type = self.config['db_type']

        if db_type == 'postgresql':
            import asyncpg
            self.connection = await asyncpg.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database']
            )

        elif db_type == 'mongodb':
            from motor import motor_asyncio
            self.client = motor_asyncio.AsyncIOMotorClient(
                self.config['connection_string']
            )
            self.connection = self.client[self.config['database']]

        logger.info(f"Connected to {db_type} database")

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute database action"""

        if action == "query_data":
            return await self._query(params['sql'], params.get('params', []))

        elif action == "insert_data":
            return await self._insert(params['table'], params['data'])

        elif action == "schema_introspection":
            return await self._introspect_schema(params.get('table'))

        else:
            raise ValueError(f"Unknown action: {action}")

    async def _query(self, sql: str, params: List = None):
        """Execute SQL query"""
        if self.config['db_type'] == 'postgresql':
            return await self.connection.fetch(sql, *params)

    async def _insert(self, table: str, data: Dict):
        """Insert data"""
        if self.config['db_type'] == 'postgresql':
            columns = ', '.join(data.keys())
            values = ', '.join([f'${i+1}' for i in range(len(data))])
            sql = f"INSERT INTO {table} ({columns}) VALUES ({values})"
            await self.connection.execute(sql, *data.values())

    async def _introspect_schema(self, table: str = None):
        """Get database schema"""
        if self.config['db_type'] == 'postgresql':
            if table:
                sql = """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = $1
                """
                return await self.connection.fetch(sql, table)
            else:
                sql = """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """
                return await self.connection.fetch(sql)

    def _list_actions(self):
        return [
            {
                'name': 'query_data',
                'description': 'Execute SQL query',
                'params': {
                    'sql': 'string',
                    'params': 'array (optional)'
                }
            },
            {
                'name': 'insert_data',
                'description': 'Insert data into table',
                'params': {
                    'table': 'string',
                    'data': 'object'
                }
            },
            {
                'name': 'schema_introspection',
                'description': 'Get database schema',
                'params': {
                    'table': 'string (optional)'
                }
            }
        ]
```

### Configuração

```yaml
# config/integrations/postgres.yaml

integration_agents:
  - agent_id: "postgres-main"
    service_type: "database"
    db_type: "postgresql"
    host: "localhost"
    port: 5432
    user: "ch8agent"
    password: "${POSTGRES_PASSWORD}"
    database: "production"
    pool_size: 10
    timeout: 30

  - agent_id: "mongo-analytics"
    service_type: "database"
    db_type: "mongodb"
    connection_string: "mongodb://localhost:27017"
    database: "analytics"
```

### Uso em um Agent Node

```python
# Dentro de um AgentNode

async def use_database(self, task):
    """Use database integration agent"""

    # 1. Get database integration agent
    db_agent = self.integration_agents['postgres-main']

    # 2. Query data
    results = await db_agent.execute_action(
        action='query_data',
        params={
            'sql': 'SELECT * FROM users WHERE active = $1',
            'params': [True]
        }
    )

    # 3. Process results with LLM
    analysis = await self.llm.analyze(results)

    return analysis
```

---

## 🌐 Exemplo: API Integration Agent

```python
# cluster/integration/api_agent.py

class APIIntegrationAgent(MCPIntegrationAgent):
    """
    MCP Integration Agent for REST APIs
    """

    def _define_capabilities(self):
        return [
            "http_get",
            "http_post",
            "http_put",
            "http_delete",
            "graphql_query",
            "webhook_subscribe"
        ]

    async def connect(self):
        """Setup HTTP client"""
        import aiohttp
        self.session = aiohttp.ClientSession(
            base_url=self.config['base_url'],
            headers={
                'Authorization': f"Bearer {self.config['api_key']}",
                'Content-Type': 'application/json'
            }
        )

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute API action"""

        if action == "http_get":
            async with self.session.get(
                params['path'],
                params=params.get('query')
            ) as response:
                return await response.json()

        elif action == "http_post":
            async with self.session.post(
                params['path'],
                json=params['body']
            ) as response:
                return await response.json()

        elif action == "graphql_query":
            async with self.session.post(
                '/graphql',
                json={'query': params['query'], 'variables': params.get('variables')}
            ) as response:
                return await response.json()

    def _list_actions(self):
        return [
            {
                'name': 'http_get',
                'description': 'HTTP GET request',
                'params': {
                    'path': 'string',
                    'query': 'object (optional)'
                }
            },
            {
                'name': 'http_post',
                'description': 'HTTP POST request',
                'params': {
                    'path': 'string',
                    'body': 'object'
                }
            },
            {
                'name': 'graphql_query',
                'description': 'Execute GraphQL query',
                'params': {
                    'query': 'string',
                    'variables': 'object (optional)'
                }
            }
        ]
```

### Configuração

```yaml
# config/integrations/apis.yaml

integration_agents:
  - agent_id: "github-api"
    service_type: "api"
    base_url: "https://api.github.com"
    api_key: "${GITHUB_TOKEN}"
    rate_limit: 5000

  - agent_id: "slack-api"
    service_type: "api"
    base_url: "https://slack.com/api"
    api_key: "${SLACK_TOKEN}"
```

---

## 🧠 Exemplo: RAG Integration Agent

```python
# cluster/integration/rag_agent.py

class RAGIntegrationAgent(MCPIntegrationAgent):
    """
    MCP Integration Agent for RAG systems
    Integrates with vector databases and semantic search
    """

    def _define_capabilities(self):
        return [
            "semantic_search",
            "index_documents",
            "delete_documents",
            "update_embeddings",
            "similarity_search"
        ]

    async def connect(self):
        """Connect to vector database"""
        if self.config['vector_db'] == 'pinecone':
            import pinecone
            pinecone.init(
                api_key=self.config['api_key'],
                environment=self.config['environment']
            )
            self.index = pinecone.Index(self.config['index_name'])

        elif self.config['vector_db'] == 'weaviate':
            import weaviate
            self.client = weaviate.Client(self.config['url'])

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute RAG action"""

        if action == "semantic_search":
            # Get query embedding
            query_embedding = await self._get_embedding(params['query'])

            # Search vector DB
            results = self.index.query(
                query_embedding,
                top_k=params.get('top_k', 10),
                include_metadata=True
            )

            return results

        elif action == "index_documents":
            # Convert documents to embeddings
            embeddings = await self._batch_embed(params['documents'])

            # Upsert to vector DB
            self.index.upsert(
                vectors=list(zip(
                    params['ids'],
                    embeddings,
                    params['metadata']
                ))
            )

    async def _get_embedding(self, text: str):
        """Get embedding from model"""
        # Use local embedding model or API
        if self.config['embedding_model'] == 'local':
            return await self.local_embedder.encode(text)
        else:
            return await self.openai_embed(text)

    def _list_actions(self):
        return [
            {
                'name': 'semantic_search',
                'description': 'Search documents by semantic similarity',
                'params': {
                    'query': 'string',
                    'top_k': 'integer (optional, default 10)'
                }
            },
            {
                'name': 'index_documents',
                'description': 'Index new documents',
                'params': {
                    'documents': 'array of strings',
                    'ids': 'array of strings',
                    'metadata': 'array of objects'
                }
            }
        ]
```

---

## 🔌 Integration Agent Manager

```python
# cluster/integration/manager.py

class IntegrationAgentManager:
    """
    Manages all integration agents for a node
    """

    def __init__(self, node_id):
        self.node_id = node_id
        self.agents: Dict[str, MCPIntegrationAgent] = {}
        self.agent_registry = {}

    async def load_agents(self, config_path: str):
        """Load integration agents from config"""

        # Load config
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Create agents
        for agent_config in config['integration_agents']:
            agent = self._create_agent(agent_config)
            await agent.connect()
            self.agents[agent.agent_id] = agent

            # Register capabilities
            self.agent_registry[agent.agent_id] = await agent.get_capabilities()

        logger.info(f"Loaded {len(self.agents)} integration agents")

    def _create_agent(self, config):
        """Factory method for creating agents"""

        service_type = config['service_type']

        if service_type == 'database':
            return DatabaseIntegrationAgent(config)
        elif service_type == 'api':
            return APIIntegrationAgent(config)
        elif service_type == 'rag':
            return RAGIntegrationAgent(config)
        elif service_type == 'filesystem':
            return FilesystemIntegrationAgent(config)
        else:
            # Dynamic plugin loading
            return self._load_plugin(service_type, config)

    async def execute(self, agent_id: str, action: str, params: Dict) -> Any:
        """Execute action on integration agent"""

        if agent_id not in self.agents:
            raise ValueError(f"Integration agent not found: {agent_id}")

        agent = self.agents[agent_id]
        return await agent.execute(action, params)

    async def share_agent(self, agent_id: str, peer_node_id: str):
        """Share integration agent with peer node"""

        if agent_id not in self.agents:
            return False

        # Announce agent to peer
        await self.messenger.send_message(
            peer_node_id,
            {
                'type': 'integration_agent_offer',
                'payload': {
                    'agent_id': agent_id,
                    'capabilities': self.agent_registry[agent_id],
                    'node_id': self.node_id
                }
            }
        )

        return True

    async def use_remote_agent(self, peer_node_id: str, agent_id: str,
                                action: str, params: Dict) -> Any:
        """Use integration agent from another node"""

        # Request action via P2P
        response = await self.messenger.send_message(
            peer_node_id,
            {
                'type': 'integration_agent_request',
                'payload': {
                    'agent_id': agent_id,
                    'action': action,
                    'params': params
                }
            }
        )

        return response
```

---

## 🎯 Use Cases

### Use Case 1: Multi-Database Query

```python
# Node 1 tem PostgreSQL
# Node 2 tem MongoDB
# Node 3 precisa consultar ambos

async def multi_db_query(self):
    # Query PostgreSQL on Node 1
    pg_results = await self.use_remote_agent(
        peer_node_id='node-1',
        agent_id='postgres-main',
        action='query_data',
        params={'sql': 'SELECT * FROM users'}
    )

    # Query MongoDB on Node 2
    mongo_results = await self.use_remote_agent(
        peer_node_id='node-2',
        agent_id='mongo-analytics',
        action='find',
        params={'collection': 'events', 'query': {}}
    )

    # Combine and analyze
    combined = self.merge_results(pg_results, mongo_results)
    return await self.llm.analyze(combined)
```

### Use Case 2: RAG + API Integration

```python
async def research_and_fetch(self, topic: str):
    # 1. Semantic search in RAG
    docs = await self.integration_agents['rag-docs'].execute_action(
        'semantic_search',
        {'query': topic, 'top_k': 5}
    )

    # 2. Fetch latest data from API
    api_data = await self.integration_agents['github-api'].execute_action(
        'http_get',
        {'path': f'/search/repositories?q={topic}'}
    )

    # 3. Combine and synthesize
    return await self.synthesize(docs, api_data)
```

---

## 📊 MCP Protocol Format

### Agent Capabilities Announcement

```json
{
  "agent_id": "postgres-main",
  "service_type": "database",
  "mcp_version": "1.0",
  "capabilities": [
    "query_data",
    "insert_data",
    "schema_introspection"
  ],
  "actions": [
    {
      "name": "query_data",
      "description": "Execute SQL query",
      "params": {
        "sql": "string",
        "params": "array"
      },
      "returns": "array of objects"
    }
  ],
  "health": "healthy",
  "node_id": "node-1",
  "shareable": true
}
```

---

## 🚀 Next Steps

### Sprint 3: MCP Integration Layer

1. **Base Interface** - MCPIntegrationAgent class
2. **Core Agents** - Database, API, RAG
3. **Agent Manager** - Load, register, execute
4. **P2P Sharing** - Share agents across nodes
5. **Plugin System** - Dynamic agent loading

---

**Status:** Design completo, pronto para implementação
**Autor:** Hudson RJ + Claude
**Data:** 2026-04-21
