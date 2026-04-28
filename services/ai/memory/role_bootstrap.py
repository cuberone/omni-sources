"""Sync the mem0ai role's password from the env var to Postgres.

Schema setup (CREATE ROLE, GRANT/REVOKE, ALTER DEFAULT PRIVILEGES) lives
in migration 085_create_mem0ai_role.sql which the migrator runs once
before any AI worker starts. The role is created NOLOGIN there.

This module flips it to LOGIN with the env-supplied password and
re-rotates on every boot. A Postgres advisory lock serializes the N
uvicorn workers that all hit this code path at startup, so they don't
race on `pg_authid` and emit `tuple concurrently updated` errors.
"""
import logging
import re

import psycopg

logger = logging.getLogger(__name__)

# Plain unquoted Postgres identifier — safe to inline into ALTER ROLE.
_ROLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Stable arbitrary 64-bit advisory-lock key. Session-scoped; auto-released
# on connection close. Hex of "mem0_pwd" packed.
_PASSWORD_LOCK_KEY = 0x6D656D305F707764


def sync_mem0ai_password(
    dsn: str,
    mem0ai_password: str | None,
    role_name: str = "mem0ai",
) -> None:
    """Set the mem0ai role's password (LOGIN) from the env var.

    Args:
        dsn: Privileged connection string (the main omni role).
        mem0ai_password: Plaintext password to sync.
        role_name: Postgres role name. Defaults to ``mem0ai``.

    Raises:
        ValueError: if `mem0ai_password` is missing or `role_name` is not
            a plain identifier.
    """
    if not mem0ai_password:
        raise ValueError(
            "MEM0AI_DATABASE_ROLE_PASSWORD is required when MEMORY_ENABLED=true"
        )
    if not _ROLE_NAME_RE.match(role_name):
        raise ValueError(f"Invalid mem0ai role name: {role_name!r}")

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        # Serialize concurrent workers so two ALTER ROLEs don't collide on
        # pg_authid. Lock auto-releases when the connection closes.
        cur.execute("SELECT pg_advisory_lock(%s)", (_PASSWORD_LOCK_KEY,))
        cur.execute(
            f"SELECT format('ALTER ROLE {role_name} WITH LOGIN PASSWORD %%L', %s::text)",
            (mem0ai_password,),
        )
        cur.execute(cur.fetchone()[0])

    logger.info(f"{role_name} password synced")
