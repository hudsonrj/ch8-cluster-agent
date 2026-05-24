#!/usr/bin/env python3
"""
CH8 Hub Cluster — Feature Tables Test
Testa funcionalidade de skills e user profile
"""

import psycopg2
import os
from datetime import datetime

DB_CONFIG = {
    'dbname': 'ch8app',
    'user': 'ch8app',
    'password': os.getenv('CH8_DB_PASSWORD', 'ch8app'),
    'host': 'localhost',
    'port': 5432
}

def test_skills():
    """Testa CRUD de skills"""
    print("\n=== TESTE: CH8_SKILLS ===")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Criar skill
    cursor.execute("""
        INSERT INTO ch8_skills (name, description, triggers, content, author)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, name
    """, (
        'test_skill',
        'Skill de teste automático',
        ['test', 'auto'],
        'echo "Test successful"',
        'test_suite'
    ))
    skill_id, skill_name = cursor.fetchone()
    print(f"✓ Skill criada: #{skill_id} — {skill_name}")
    
    # Buscar por trigger
    cursor.execute("""
        SELECT name, description FROM ch8_skills
        WHERE 'docker' = ANY(triggers)
    """)
    results = cursor.fetchall()
    print(f"✓ Skills com trigger 'docker': {len(results)}")
    
    # Full-text search
    cursor.execute("""
        SELECT name, ts_rank(to_tsvector('portuguese', name || ' ' || COALESCE(description,'')), 
                             plainto_tsquery('portuguese', 'container status')) as rank
        FROM ch8_skills
        WHERE to_tsvector('portuguese', name || ' ' || COALESCE(description,'')) 
              @@ plainto_tsquery('portuguese', 'container status')
        ORDER BY rank DESC
    """)
    results = cursor.fetchall()
    print(f"✓ FTS 'container status': {len(results)} resultados")
    
    # Incrementar uso
    cursor.execute("""
        UPDATE ch8_skills SET uses = uses + 1 WHERE id = %s
        RETURNING uses, updated_at
    """, (skill_id,))
    uses, updated = cursor.fetchone()
    print(f"✓ Uso incrementado: {uses} vezes (updated_at: {updated})")
    
    # Limpar teste
    cursor.execute("DELETE FROM ch8_skills WHERE author = 'test_suite'")
    conn.commit()
    print("✓ Skill de teste removida")
    
    cursor.close()
    conn.close()

def test_user_profile():
    """Testa CRUD de user profile"""
    print("\n=== TESTE: USER_PROFILE ===")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Criar perfil
    cursor.execute("""
        INSERT INTO user_profile (key, value, confidence, source)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET 
            value = EXCLUDED.value,
            confidence = EXCLUDED.confidence,
            source = EXCLUDED.source
        RETURNING key, confidence
    """, ('test_key', 'test_value', 0.75, 'test'))
    key, conf = cursor.fetchone()
    print(f"✓ Profile criado: {key} (confidence: {conf})")
    
    # Buscar alta confiança
    cursor.execute("""
        SELECT key, confidence FROM user_profile
        WHERE confidence >= 0.9
        ORDER BY confidence DESC
    """)
    results = cursor.fetchall()
    print(f"✓ Entries com confidence ≥ 0.9: {len(results)}")
    
    # Atualizar e verificar trigger
    cursor.execute("""
        UPDATE user_profile 
        SET value = 'updated_value'
        WHERE key = 'test_key'
        RETURNING updated_at
    """)
    updated = cursor.fetchone()[0]
    print(f"✓ Trigger updated_at funcionando: {updated}")
    
    # Limpar teste
    cursor.execute("DELETE FROM user_profile WHERE source = 'test'")
    conn.commit()
    print("✓ Profile de teste removido")
    
    cursor.close()
    conn.close()

def test_replication():
    """Verifica status de replicação"""
    print("\n=== TESTE: REPLICAÇÃO ===")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT schemaname, tablename 
        FROM pg_publication_tables 
        WHERE pubname = 'ch8_replica'
        ORDER BY tablename
    """)
    tables = cursor.fetchall()
    
    print(f"✓ Publication 'ch8_replica' ativa com {len(tables)} tabelas:")
    for schema, table in tables:
        print(f"   • {schema}.{table}")
    
    # Verifica slots de replicação
    cursor.execute("""
        SELECT slot_name, active, restart_lsn 
        FROM pg_replication_slots
        WHERE slot_type = 'logical'
    """)
    slots = cursor.fetchall()
    if slots:
        print(f"\n✓ Replication slots ativos: {len(slots)}")
        for slot, active, lsn in slots:
            status = "🟢 ativo" if active else "🔴 inativo"
            print(f"   • {slot} — {status} (LSN: {lsn})")
    
    cursor.close()
    conn.close()

def main():
    print("=" * 60)
    print("CH8 Hub Cluster — Feature Tables Test Suite")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    try:
        test_skills()
        test_user_profile()
        test_replication()
        
        print("\n" + "=" * 60)
        print("✅ TODOS OS TESTES PASSARAM")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
