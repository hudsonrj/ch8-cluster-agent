#!/usr/bin/env python3

import json
import psycopg2
import psycopg2.extras
import time
import logging
import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - PostgreSQL-agent - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

class PostgreSQLAgent:
    def __init__(self):
        self.agent_id = "PostgreSQL-agent"
        self.service_type = "database"
        self.description = "InvestAI PostgreSQL Database Agent"
        self.connection_params = {
            'host': 'localhost',
            'port': 5435,
            'database': 'investai',
            'user': 'investai',
            'password': 'investai123'
        }
        self.conn = None
        self.state_file = os.path.expanduser('~/.config/ch8/state.json')
        self.state_lock = os.path.expanduser('~/.config/ch8/state.lock')
        
    def connect(self) -> bool:
        """Establish connection to PostgreSQL"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            self.conn.autocommit = True
            logger.info("Connected to PostgreSQL database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on PostgreSQL service"""
        try:
            if not self.conn or self.conn.closed:
                if not self.connect():
                    return {'status': 'unhealthy', 'error': 'Connection failed'}
            
            with self.conn.cursor() as cur:
                cur.execute("SELECT version(), current_timestamp")
                result = cur.fetchone()
                
                # Get database size
                cur.execute("SELECT pg_size_pretty(pg_database_size('investai'))")
                db_size = cur.fetchone()[0]
                
                # Get connection count
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='investai'")
                connections = cur.fetchone()[0]
                
                return {
                    'status': 'healthy',
                    'version': result[0],
                    'timestamp': result[1].isoformat(),
                    'database_size': db_size,
                    'active_connections': connections
                }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {'status': 'unhealthy', 'error': str(e)}
    
    def execute_query(self, query: str, params: Optional[List] = None) -> Dict[str, Any]:
        """Execute SQL query"""
        try:
            if not self.conn or self.conn.closed:
                if not self.connect():
                    return {'error': 'Connection failed'}
            
            with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if params:
                    cur.execute(query, params)
                else:
                    cur.execute(query)
                
                if cur.description:
                    results = cur.fetchall()
                    return {
                        'success': True,
                        'rows': [dict(row) for row in results],
                        'rowcount': len(results)
                    }
                else:
                    return {
                        'success': True,
                        'rowcount': cur.rowcount,
                        'message': 'Query executed successfully'
                    }
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {'error': str(e)}
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get database schema information"""
        try:
            schema_info = {}
            
            # Get all tables
            tables_query = """
                SELECT table_name, table_type 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """
            tables_result = self.execute_query(tables_query)
            
            if 'rows' in tables_result:
                schema_info['tables'] = tables_result['rows']
                
                # Get columns for each table
                for table in tables_result['rows']:
                    table_name = table['table_name']
                    columns_query = """
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns 
                        WHERE table_name = %s AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """
                    columns_result = self.execute_query(columns_query, [table_name])
                    if 'rows' in columns_result:
                        table['columns'] = columns_result['rows']
            
            return schema_info
        except Exception as e:
            logger.error(f"Schema info failed: {e}")
            return {'error': str(e)}
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get database metrics"""
        try:
            metrics = {}
            
            # Database statistics
            stats_query = """
                SELECT 
                    numbackends as active_connections,
                    xact_commit as transactions_committed,
                    xact_rollback as transactions_rolled_back,
                    blks_read as blocks_read,
                    blks_hit as blocks_hit,
                    tup_returned as tuples_returned,
                    tup_fetched as tuples_fetched,
                    tup_inserted as tuples_inserted,
                    tup_updated as tuples_updated,
                    tup_deleted as tuples_deleted
                FROM pg_stat_database 
                WHERE datname = 'investai'
            """
            
            result = self.execute_query(stats_query)
            if 'rows' in result and result['rows']:
                metrics['database_stats'] = result['rows'][0]
            
            # Table sizes
            size_query = """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """
            
            result = self.execute_query(size_query)
            if 'rows' in result:
                metrics['table_sizes'] = result['rows']
            
            return metrics
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return {'error': str(e)}
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return the MCP tools this agent exposes."""
        return [
            {
                "name": "health_check",
                "description": "Check PostgreSQL database health, version, size, and connections",
            },
            {
                "name": "execute_query",
                "description": "Execute a SQL query against the investai database",
                "parameters": {"query": "string", "params": "list (optional)"},
            },
            {
                "name": "get_schema_info",
                "description": "Get full database schema: tables, columns, types",
            },
            {
                "name": "get_metrics",
                "description": "Get database performance metrics: stats, table sizes, connections",
            },
        ]

    def register_agent(self, status="running", task=""):
        """Register this agent in the state file (compatible with ch8 dashboard)."""
        import fcntl
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_lock, 'w') as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                state = {}
                if os.path.exists(self.state_file):
                    with open(self.state_file, 'r') as f:
                        state = json.load(f)

                agents = state.get('agents', [])
                if isinstance(agents, dict):
                    agents = []
                agents = [a for a in agents if a.get('name') != self.agent_id]
                agents.append({
                    'name': self.agent_id,
                    'status': status,
                    'task': task or f"monitoring {self.connection_params['database']}",
                    'model': 'PostgreSQL MCP',
                    'platform': 'database',
                    'autonomous': False,
                    'alerts': 0,
                    'security_findings': 0,
                    'predictions': 0,
                    'heavy_procs': 0,
                    'tools': [t["name"] for t in self.get_tools()],
                    'details': {
                        'mcp_tools': self.get_tools(),
                        'connection': {
                            'host': self.connection_params['host'],
                            'port': self.connection_params['port'],
                            'database': self.connection_params['database'],
                        },
                    },
                    'updated_at': int(time.time()),
                })
                state['agents'] = agents
                with open(self.state_file, 'w') as f:
                    json.dump(state, f, indent=2)
                fcntl.flock(lf, fcntl.LOCK_UN)
            logger.info(f"Agent {self.agent_id} registered successfully")
        except Exception as e:
            logger.error(f"Failed to register agent: {e}")
    
    def run_monitoring_loop(self):
        """Main monitoring loop"""
        logger.info(f"Starting {self.agent_id} monitoring loop")

        while True:
            try:
                health = self.health_check()
                if health['status'] == 'healthy':
                    task = f"healthy · {health.get('active_connections',0)} conns · {health.get('database_size','?')}"
                    self.register_agent("running", task)
                else:
                    self.register_agent("error", health.get('error','unhealthy')[:60])

                time.sleep(30)

            except KeyboardInterrupt:
                logger.info("Agent stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self.register_agent("error", str(e)[:60])
                time.sleep(10)
    
    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP-style tool calls"""
        if tool_name == 'health_check':
            return self.health_check()
        elif tool_name == 'execute_query':
            return self.execute_query(args.get('query'), args.get('params'))
        elif tool_name == 'get_schema_info':
            return self.get_schema_info()
        elif tool_name == 'get_metrics':
            return self.get_metrics()
        else:
            return {'error': f'Unknown tool: {tool_name}'}

def main():
    agent = PostgreSQLAgent()
    
    # Test initial connection
    if not agent.connect():
        logger.error("Failed to connect to PostgreSQL. Exiting.")
        sys.exit(1)
    
    # Register agent
    agent.register_agent()
    
    # Start monitoring loop
    try:
        agent.run_monitoring_loop()
    except Exception as e:
        logger.error(f"Agent crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
