"""
CH8 Vault — Encrypted credential store for the cluster.

Stores all service passwords, tokens, and connection strings in an
AES-encrypted vault file. Agents use vault.get("service/key") to retrieve
credentials without ever seeing them in plaintext in code.

Architecture:
  - Master vault: /root/.config/ch8/vault.enc (encrypted with master key)
  - Master key: /root/.config/ch8/vault.key (chmod 600, never committed)
  - Backup: PostgreSQL cluster_state (encrypted blob in vault_backup column)
  - Replica: Automatically replicated to vmi via PG streaming
  - API: vault.get(path), vault.set(path, value), vault.list()
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Optional, Dict

log = logging.getLogger("ch8.vault")

CONFIG_DIR = Path(os.environ.get("CH8_CONFIG_DIR", Path.home() / ".config" / "ch8"))
VAULT_FILE = CONFIG_DIR / "vault.enc"
KEY_FILE = CONFIG_DIR / "vault.key"


def _ensure_key() -> bytes:
    """Load or generate the master encryption key."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    log.info("Generated new vault master key")
    return key


def _get_fernet():
    from cryptography.fernet import Fernet
    return Fernet(_ensure_key())


def _load_vault() -> Dict:
    """Decrypt and load vault contents."""
    if not VAULT_FILE.exists():
        return {"secrets": {}, "metadata": {"created_at": int(time.time()), "version": 1}}
    try:
        f = _get_fernet()
        encrypted = VAULT_FILE.read_bytes()
        decrypted = f.decrypt(encrypted)
        return json.loads(decrypted)
    except Exception as e:
        log.error(f"Failed to decrypt vault: {e}")
        return {"secrets": {}, "metadata": {"created_at": int(time.time()), "version": 1}}


def _save_vault(vault: Dict) -> None:
    """Encrypt and save vault to disk."""
    vault["metadata"]["updated_at"] = int(time.time())
    f = _get_fernet()
    encrypted = f.encrypt(json.dumps(vault).encode())
    VAULT_FILE.write_bytes(encrypted)
    VAULT_FILE.chmod(0o600)
    # Also backup to PostgreSQL (encrypted)
    _backup_to_db(encrypted)


def _backup_to_db(encrypted_blob: bytes) -> None:
    """Save encrypted vault to PostgreSQL for disaster recovery."""
    try:
        db_url = os.environ.get("CH8_DB_URL", "")
        if not db_url:
            env_file = CONFIG_DIR / "env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("CH8_DB_URL="):
                        db_url = line.split("=", 1)[1].strip()
        if not db_url:
            return
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vault_backup (id, encrypted_data, updated_at)
            VALUES (1, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET encrypted_data=EXCLUDED.encrypted_data, updated_at=NOW()
        """, (encrypted_blob,))
        conn.commit()
        conn.close()
        log.info("Vault backed up to PostgreSQL")
    except Exception as e:
        log.warning(f"Vault DB backup failed: {e}")


def get(path: str) -> Optional[str]:
    """Get a secret by path (e.g., 'oracle/password', 'ch8_cluster/db_url')."""
    vault = _load_vault()
    return vault["secrets"].get(path)


def set(path: str, value: str, description: str = "") -> None:
    """Set a secret at path."""
    vault = _load_vault()
    vault["secrets"][path] = value
    if "descriptions" not in vault:
        vault["descriptions"] = {}
    if description:
        vault["descriptions"][path] = description
    _save_vault(vault)
    log.info(f"Vault: set {path}")


def delete(path: str) -> bool:
    """Delete a secret."""
    vault = _load_vault()
    if path in vault["secrets"]:
        del vault["secrets"][path]
        _save_vault(vault)
        log.info(f"Vault: deleted {path}")
        return True
    return False


def list_keys() -> list:
    """List all secret paths (not values)."""
    vault = _load_vault()
    return sorted(vault["secrets"].keys())


def get_all() -> Dict[str, str]:
    """Get all secrets (for internal agent use only)."""
    vault = _load_vault()
    return dict(vault["secrets"])


def get_connection_string(service: str) -> Optional[str]:
    """Get a database connection string by service name."""
    # Try specific patterns
    for pattern in [f"{service}/url", f"{service}/db_url", f"{service}/connection_string"]:
        val = get(pattern)
        if val:
            return val
    return None


def initialize_from_env() -> int:
    """Populate vault from existing env files and known credentials."""
    count = 0

    # From ~/.config/ch8/env
    env_file = CONFIG_DIR / "env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                path = f"env/{key}"
                if not get(path):
                    set(path, value, f"From ch8 env file")
                    count += 1

    # Known service passwords
    known = {
        "oracle/system_password": "oracle",
        "oracle/connection": "system/oracle@//localhost:1521/FREEPDB1",
        "ch8_cluster/db_url": "postgresql://ch8app:ch8cluster2024@127.0.0.1:5432/ch8_cluster",
        "ch8_cluster/password": "ch8cluster2024",
        "ch8_cluster/admin_password": "pg_ch8_admin",
        "govgpt/postgres_password": "govgpt_analytics_2026",
        "escolavalor/postgres_password": "Esc0l4Val0r2026Sec",
        "escolavalor/redis_password": "R3d1s_Esc0la_2026!",
        "redis/password": "",  # ch8-redis has no password
    }
    for path, value in known.items():
        if not get(path):
            set(path, value, f"Known service credential")
            count += 1

    return count
