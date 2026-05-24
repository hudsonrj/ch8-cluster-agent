#!/usr/bin/env python3
"""
CH8 Hub Cluster — Feature Tables Setup
Cria tabelas de skills e user profile com replicação
Autor: Nikolas (DBA CH8)
Ticket: TKT-20260521-0026
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import sys
from datetime import datetime

# Configuração de conexão - usando govgpt-postgres container
DB_CONFIG = {
    'dbname': 'ch8app',
    'user': 'govgpt',
    'password': os.getenv('POSTGRES_PASSWORD', 'govgpt'),
    'host': '127.0.0.1',
    'port': 5433
}

# DDL Statements
TABLES_DDL = [
    """
    -- Tabela de Skills personalizáveis
    CREATE TABLE IF NOT EXISTS ch8_skills (
        id SERIAL PRIMARY KEY,
        name VARCHAR(200) UNIQUE NOT NULL,
        description TEXT,
        triggers TEXT[],
        content TEXT NOT NULL,
        author VARCHAR(100) DEFAULT 'system',
        uses INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    
    """
    -- Tabela de User Profile (chave-valor com confiança)
    CREATE TABLE IF NOT EXISTS user_profile (
        key VARCHAR(200) PRIMARY KEY,
        value TEXT NOT NULL,
        confidence FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
        source VARCHAR(100) DEFAULT 'system',
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,
    
    """
    -- Índice full-text para mensagens (português)
    CREATE INDEX IF NOT EXISTS chat_fts ON chat_messages 
    USING gin(to_tsvector('portuguese', content));
    """,
    
    """
    -- Índice full-text para skills (português)
    CREATE INDEX IF NOT EXISTS skills_fts ON ch8_skills 
    USING gin(to_tsvector('portuguese', name || ' ' || COALESCE(description,'')));
    """,
    
    """
    -- Índice de uso para ranking de skills
    CREATE INDEX IF NOT EXISTS idx_skills_uses ON ch8_skills(uses DESC);
    """,
    
    """
    -- Índice de confiança para user profile
    CREATE INDEX IF NOT EXISTS idx_profile_confidence ON user_profile(confidence DESC);
    """
]

# Trigger de atualização automática
TRIGGER_DDL = """
-- Trigger para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_skills_updated_at ON ch8_skills;
CREATE TRIGGER update_skills_updated_at 
    BEFORE UPDATE ON ch8_skills 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_profile_updated_at ON user_profile;
CREATE TRIGGER update_profile_updated_at 
    BEFORE UPDATE ON user_profile 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
"""

# Seeds iniciais
SEEDS = [
    """
    INSERT INTO ch8_skills (name, description, triggers, content, author) 
    VALUES 
        ('docker_status', 'Mostra status de containers Docker', 
         ARRAY['containers', 'docker', 'status'], 
         'docker ps -a --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"',
         'nikolas'),
        ('disk_usage', 'Verifica uso de disco por diretório',
         ARRAY['disk', 'storage', 'space'],
         'du -sh /data/* /var/* 2>/dev/null | sort -hr | head -20',
         'nikolas'),
        ('node_health', 'Health check completo do nó',
         ARRAY['health', 'status', 'sistema'],
         'echo "CPU: $(top -bn1 | grep Cpu | awk ''{print $2}'')% | RAM: $(free | grep Mem | awk ''{print ($3/$2)*100}'')% | Disk: $(df -h / | tail -1 | awk ''{print $5}'')"',
         'nikolas')
    ON CONFLICT (name) DO NOTHING;
    """,
    
    """
    INSERT INTO user_profile (key, value, confidence, source)
    VALUES
        ('preferred_language', 'pt-BR', 1.0, 'system'),
        ('timezone', 'America/Sao_Paulo', 1.0, 'system'),
        ('role', 'sysadmin', 0.9, 'inferred'),
        ('expertise', 'devops,postgresql,docker', 0.85, 'behavioral')
    ON CONFLICT (key) DO NOTHING;
    """
]

def execute_sql(cursor, sql, description):
    """Executa SQL com tratamento de erro"""
    try:
        cursor.execute(sql)
        print(f"✓ {description}")
        return True
    except Exception as e:
        print(f"✗ {description}: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("CH8 Hub Cluster — Feature Tables Setup")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Target: govgpt-postgres:5433/ch8app")
    print("=" * 60)
    
    conn = None
    try:
        # Conecta ao banco
        print("\n[1] Conectando ao PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        print("✓ Conectado como govgpt@ch8app")
        
        # Cria tabelas
        print("\n[2] Criando tabelas...")
        for i, ddl in enumerate(TABLES_DDL, 1):
            execute_sql(cursor, ddl, f"Tabela/Índice {i}/{len(TABLES_DDL)}")
        
        # Cria triggers
        print("\n[3] Criando triggers...")
        execute_sql(cursor, TRIGGER_DDL, "Triggers de updated_at")
        
        # Seeds
        print("\n[4] Inserindo dados iniciais...")
        for i, seed in enumerate(SEEDS, 1):
            execute_sql(cursor, seed, f"Seed {i}/{len(SEEDS)}")
        
        # Configurar replicação
        print("\n[5] Configurando replicação lógica...")
        
        # Verifica se publication existe
        cursor.execute("""
            SELECT 1 FROM pg_publication WHERE pubname = 'ch8_replica'
        """)
        pub_exists = cursor.fetchone() is not None
        
        if pub_exists:
            # Adiciona tabelas à publication existente
            try:
                execute_sql(cursor, 
                    "ALTER PUBLICATION ch8_replica ADD TABLE ch8_skills, user_profile",
                    "Adicionando tabelas à replicação")
            except:
                print("   (Tabelas já estavam na publication)")
        else:
            # Cria publication com todas as tabelas
            execute_sql(cursor,
                "CREATE PUBLICATION ch8_replica FOR TABLE chat_messages, ch8_skills, user_profile",
                "Criando publication ch8_replica")
        
        # Verifica tabelas na publication
        cursor.execute("""
            SELECT schemaname, tablename 
            FROM pg_publication_tables 
            WHERE pubname = 'ch8_replica'
            ORDER BY tablename
        """)
        tables = cursor.fetchall()
        print("\n📋 Tabelas na replicação ch8_replica:")
        for schema, table in tables:
            print(f"   • {schema}.{table}")
        
        # Estatísticas finais
        print("\n[6] Verificando criação...")
        
        cursor.execute("SELECT COUNT(*) FROM ch8_skills")
        skills_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM user_profile")
        profile_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT indexname FROM pg_indexes 
            WHERE tablename IN ('ch8_skills', 'user_profile', 'chat_messages')
            AND indexname LIKE '%fts%'
        """)
        fts_indexes = cursor.fetchall()
        
        print(f"\n✅ SUCESSO!")
        print(f"   • Skills criadas: {skills_count}")
        print(f"   • Profile entries: {profile_count}")
        print(f"   • Índices FTS: {len(fts_indexes)}")
        print(f"   • Replicação: {len(tables)} tabelas")
        
        cursor.close()
        return 0
        
    except psycopg2.OperationalError as e:
        print(f"\n❌ ERRO de conexão: {e}")
        print("Verifique se o PostgreSQL está rodando e as credenciais estão corretas.")
        return 1
    
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if conn:
            conn.close()
            print("\n[7] Conexão fechada.")

if __name__ == '__main__':
    sys.exit(main())
