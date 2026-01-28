import os


# Ensure tests never try to use the remote Supabase pooler by default.
# `api/__init__.py` calls `load_dotenv()` on import; by setting env vars here
# (before test modules import `api`), dotenv will not override them.


def _setdefault_env(name: str, value: str) -> None:
    if os.environ.get(name) in (None, ""):
        os.environ[name] = value


# Local Postgres defaults (match docker-compose.yml defaults).
_setdefault_env("QUART_POSTGRES_HOST", "localhost")
_setdefault_env("QUART_POSTGRES_PORT", "5432")
_setdefault_env("QUART_POSTGRES_DB", "rogue_scholar")
_setdefault_env("QUART_POSTGRES_USER", "postgres")
_setdefault_env("QUART_POSTGRES_PASSWORD", "postgres")

# Auth-protected routes compare against this env var.
_setdefault_env("QUART_SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
