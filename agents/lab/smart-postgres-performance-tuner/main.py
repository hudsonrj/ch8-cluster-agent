#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import subprocess
from datetime import datetime
from collections import defaultdict, deque
from statistics import mean, median


class PostgresPerformanceTuner:
    def __init__(self, db_name='postgres', user='postgres', host='localhost', port='5432', password=None):
        self.db_name = db_name
        self.user = user
        self.host = host
        self.port = port
        self.password = password
        self.metrics_history = defaultdict(lambda: deque(maxlen=100))
        self.config_file = '/etc/postgresql/postgresql.conf'
        self.recommendations = []
        
    def execute_query(self, query):
        env = os.environ.copy()
        if self.password:
            env['PGPASSWORD'] = self.password
        
        cmd = [
            'psql',
            '-h', self.host,
            '-p', self.port,
            '-U', self.user,
            '-d', self.db_name,
            '-t',
            '-A',
            '-c', query
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return None
        except Exception as e:
            print(f"Error executing query: {e}", file=sys.stderr)
            return None
    
    def get_cache_hit_ratio(self):
        query = """
        SELECT 
            sum(heap_blks_read) as heap_read,
            sum(heap_blks_hit) as heap_hit,
            sum(heap_blks_hit) / nullif(sum(heap_blks_hit) + sum(heap_blks_read), 0) as ratio
        FROM pg_statio_user_tables;
        """
        result = self.execute_query(query)
        if result:
            parts = result.split('|')
            if len(parts) >= 3 and parts[2]:
                try:
                    return float(parts[2])
                except ValueError:
                    return None
        return None
    
    def get_connection_stats(self):
        query = """
        SELECT 
            count(*) as total,
            count(*) FILTER (WHERE state = 'active') as active,
            count(*) FILTER (WHERE state = 'idle') as idle,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
        FROM pg_stat_activity
        WHERE datname = current_database();
        """
        result = self.execute_query(query)
        if result:
            parts = result.split('|')
            if len(parts) >= 4:
                try:
                    return {
                        'total': int(parts[0]),
                        'active': int(parts[1]),
                        'idle': int(parts[2]),
                        'idle_in_transaction': int(parts[3])
                    }
                except ValueError:
                    return None
        return None
    
    def get_slow_queries(self, limit=10):
        query = f"""
        SELECT 
            query,
            calls,
            total_exec_time,
            mean_exec_time,
            max_exec_time
        FROM pg_stat_statements
        ORDER BY mean_exec_time DESC
        LIMIT {limit};
        """
        result = self.execute_query(query)
        if result:
            queries = []
            for line in result.split('\n'):
                if line:
                    parts = line.split('|')
                    if len(parts) >= 5:
                        try:
                            queries.append({
                                'query': parts[0][:100],
                                'calls': int(parts[1]),
                                'total_time': float(parts[2]),
                                'mean_time': float(parts[3]),
                                'max_time': float(parts[4])
                            })
                        except (ValueError, IndexError):
                            continue
            return queries
        return []
    
    def get_table_bloat(self):
        query = """
        SELECT 
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
            n_dead_tup,
            n_live_tup,
            CASE WHEN n_live_tup > 0 
                THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 2)
                ELSE 0 
            END as dead_tuple_percent
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 1000
        ORDER BY n_dead_tup DESC
        LIMIT 10;
        """
        result = self.execute_query(query)
        if result:
            tables = []
            for line in result.split('\n'):
                if line:
                    parts = line.split('|')
                    if len(parts) >= 6:
                        try:
                            tables.append({
                                'schema': parts[0],
                                'table': parts[1],
                                'size': parts[2],
                                'dead_tuples': int(parts[3]),
                                'live_tuples': int(parts[4]),
                                'dead_percent': float(parts[5])
                            })
                        except (ValueError, IndexError):
                            continue
            return tables
        return []
    
    def get_current_config(self):
        configs = {}
        params = ['shared_buffers', 'work_mem', 'maintenance_work_mem', 'effective_cache_size', 'max_connections']
        
        for param in params:
            query = f"SHOW {param};"
            result = self.execute_query(query)
            if result:
                configs[param] = result
        
        return configs
    
    def analyze_and_recommend(self):
        self.recommendations = []
        
        cache_ratio = self.get_cache_hit_ratio()
        if cache_ratio is not None:
            self.metrics_history['cache_hit_ratio'].append(cache_ratio)
            
            if cache_ratio < 0.90:
                self.recommendations.append({
                    'type': 'cache',
                    'severity': 'high',
                    'message': f'Cache hit ratio is low ({cache_ratio:.2%}). Consider increasing shared_buffers.',
                    'current_value': cache_ratio,
                    'suggested_action': 'Increase shared_buffers by 25%'
                })
            elif cache_ratio < 0.95:
                self.recommendations.append({
                    'type': 'cache',
                    'severity': 'medium',
                    'message': f'Cache hit ratio could be improved ({cache_ratio:.2%}).',
                    'current_value': cache_ratio,
                    'suggested_action': 'Consider increasing shared_buffers by 10-15%'
                })
        
        conn_stats = self.get_connection_stats()
        if conn_stats:
            self.metrics_history['connections'].append(conn_stats['total'])
            self.metrics_history['active_connections'].append(conn_stats['active'])
            
            if conn_stats['idle_in_transaction'] > 5:
                self.recommendations.append({
                    'type': 'connections',
                    'severity': 'high',
                    'message': f"High number of idle in transaction connections ({conn_stats['idle_in_transaction']})",
                    'current_value': conn_stats['idle_in_transaction'],
                    'suggested_action': 'Review application connection handling and set idle_in_transaction_session_timeout'
                })
            
            if conn_stats['total'] > 80:
                self.recommendations.append({
                    'type': 'connections',
                    'severity': 'medium',
                    'message': f"High number of total connections ({conn_stats['total']})",
                    'current_value': conn_stats['total'],
                    'suggested_action': 'Consider using connection pooling (pgBouncer) or increasing max_connections'
                })
        
        bloated_tables = self.get_table_bloat()
        for table in bloated_tables:
            if table['dead_percent'] > 20:
                self.recommendations.append({
                    'type': 'bloat',
                    'severity': 'high',
                    'message': f"Table {table['schema']}.{table['table']} has {table['dead_percent']:.1f}% dead tuples",
                    'current_value': table['dead_percent'],
                    'suggested_action': f"Run VACUUM ANALYZE on {table['schema']}.{table['table']}"
                })
        
        return self.recommendations
    
    def generate_report(self):
        report = {
            'timestamp': datetime.now().isoformat(),
            'metrics': {},
            'recommendations': self.recommendations,
            'config': self.get_current_config()
        }
        
        if self.metrics_history['cache_hit_ratio']:
            report['metrics']['cache_hit_ratio'] = {
                'current': self.metrics_history['cache_hit_ratio'][-1],
                'avg': mean(self.metrics_history['cache_hit_ratio']),
                'median': median(self.metrics_history['cache_hit_ratio'])
            }
        
        if self.metrics_history['connections']:
            report['metrics']['connections'] = {
                'current': self.metrics_history['connections'][-1],
                'avg': mean(self.metrics_history['connections']),
                'max': max(self.metrics_history['connections'])
            }
        
        if self.metrics_history['active_connections']:
            report['metrics']['active_connections'] = {
                'current': self.metrics_history['active_connections'][-1],
                'avg': mean(self.metrics_history['active_connections']),
                'max': max(self.metrics_history['active_connections'])
            }
        
        return report
    
    def monitor(self, duration=60, interval=5):
        print(f"Starting PostgreSQL performance monitoring for {duration} seconds...")
        print(f"Collecting metrics every {interval} seconds\n")
        
        start_time = time.time()
        iterations = 0
        
        while time.time() - start_time < duration:
            iterations += 1
            print(f"\n{'='*60}")
            print(f"Iteration {iterations} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            cache_ratio = self.get_cache_hit_ratio()
            if cache_ratio is not None:
                print(f"Cache Hit Ratio: {cache_ratio:.2%}")
            
            conn_stats = self.get_connection_stats()
            if conn_stats:
                print(f"Connections - Total: {conn_stats['total']}, Active: {conn_stats['active']}, Idle: {conn_stats['idle']}")
            
            bloated_tables = self.get_table_bloat()
            if bloated_tables:
                print(f"\nTop Bloated Tables:")
                for table in bloated_tables[:3]:
                    print(f"  - {table['schema']}.{table['table']}: {table['dead_percent']:.1f}% dead tuples")
            
            recommendations = self.analyze_and_recommend()
            if recommendations:
                print(f"\nRecommendations ({len(recommendations)}):")
                for rec in recommendations[:5]:
                    print(f"  [{rec['severity'].upper()}] {rec['message']}")
            
            time.sleep(interval)
        
        print(f"\n{'='*60}")
        print
