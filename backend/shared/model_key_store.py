"""Per-user model API keys, encrypted with the existing credential-at-rest key."""
from backend.shared.db import get_connection
from backend.shared.credential_store import _encrypt, _decrypt

_SCHEMA = """CREATE TABLE IF NOT EXISTS model_credentials (
    user_id TEXT PRIMARY KEY,
    encrypted_credentials TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)"""


def get_model_key(user_id: str) -> str | None:
    with get_connection() as conn:
        conn.execute(_SCHEMA)
        row = conn.execute('SELECT encrypted_credentials FROM model_credentials WHERE user_id = %s', (user_id,)).fetchone()
        conn.commit()
    return (_decrypt(row[0]).get('anthropic_api_key') or None) if row else None


def save_model_key(user_id: str, api_key: str) -> None:
    with get_connection() as conn:
        conn.execute(_SCHEMA)
        if not api_key:
            conn.execute('DELETE FROM model_credentials WHERE user_id = %s', (user_id,))
        else:
            conn.execute('''INSERT INTO model_credentials (user_id, encrypted_credentials)
                VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE
                SET encrypted_credentials = EXCLUDED.encrypted_credentials, updated_at = NOW()''',
                (user_id, _encrypt({'anthropic_api_key': api_key})))
        conn.commit()
