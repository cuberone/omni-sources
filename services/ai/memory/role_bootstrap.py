"""Ensure the restricted `mem0ai` Postgres role exists with correct grants.

Runs at AI-service startup against the privileged omni DB connection
(the one the application itself uses). Idempotent: safe to call on
every boot — creates the role only if missing, re-applies the grants
and revokes unconditionally so policy drift is self-healing.
"""
import logging

import psycopg

logger = logging.getLogger(__name__)

_ROLE = "mem0ai"


def ensure_mem0ai_role(
    dsn: str,
    database_name: str,
    database_username: str,
    mem0ai_password: str | None,
) -> None:
    """Create the mem0ai role if missing and (re)apply its grants/revokes.

    Args:
        dsn: Privileged connection string (the main omni role).
        database_name: Main omni DB name — used in `GRANT CONNECT`.
        database_username: Owner of public tables — used in
            `ALTER DEFAULT PRIVILEGES FOR ROLE` so future omni migrations
            do not silently grant access to mem0ai.
        mem0ai_password: Plaintext password for the mem0ai role login.

    Raises:
        ValueError: if `mem0ai_password` is missing. This makes a silent
            misconfig impossible — memory cannot run without it.
    """
    if not mem0ai_password:
        raise ValueError(
            "MEM0AI_DATABASE_PASSWORD is required when MEMORY_ENABLED=true"
        )

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (_ROLE,))
        exists = cur.fetchone() is not None

        if not exists:
            # Identifier (role name) is a constant; password is quoted by
            # format() with %L which produces a safe SQL string literal.
            cur.execute(
                "SELECT format('CREATE ROLE mem0ai LOGIN PASSWORD %%L', %s::text)",
                (mem0ai_password,),
            )
            create_stmt = cur.fetchone()[0]
            cur.execute(create_stmt)
            logger.info("Created mem0ai role")
        else:
            # Rotate the password on every startup so the env var is the
            # source of truth — operators can change it without manual SQL.
            cur.execute(
                "SELECT format('ALTER ROLE mem0ai PASSWORD %%L', %s::text)",
                (mem0ai_password,),
            )
            cur.execute(cur.fetchone()[0])

        # Connect and basic schema access.
        cur.execute(
            f'GRANT CONNECT ON DATABASE "{database_name}" TO mem0ai'
        )
        cur.execute("GRANT USAGE, CREATE ON SCHEMA public TO mem0ai")

        # Reassign any pre-existing mem0 tables to mem0ai. Guards against
        # a prior boot creating them under the privileged role (e.g. when
        # the initial connection config was wrong); without this, mem0
        # fails on startup with "must be owner of table ...".
        cur.execute(
            "DO $$ DECLARE r RECORD; BEGIN "
            "FOR r IN SELECT tablename FROM pg_tables "
            "WHERE schemaname='public' AND tablename LIKE 'mem0%' "
            "AND tableowner <> 'mem0ai' LOOP "
            "EXECUTE format('ALTER TABLE public.%I OWNER TO mem0ai', r.tablename); "
            "END LOOP; END $$;"
        )

        # Strip grants on existing omni tables.
        cur.execute("REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM mem0ai")
        cur.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mem0ai")
        cur.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM mem0ai")

        # The blanket REVOKE above also strips mem0ai's access to its own
        # mem0_* tables (ownership remains, but the explicit-empty ACL
        # overrides the owner's implicit grants). Restore DML privileges on
        # every mem0* table and its sequences.
        cur.execute(
            "DO $$ DECLARE r RECORD; BEGIN "
            "FOR r IN SELECT tablename FROM pg_tables "
            "WHERE schemaname='public' AND tablename LIKE 'mem0%' LOOP "
            "EXECUTE format('GRANT ALL ON TABLE public.%I TO mem0ai', r.tablename); "
            "END LOOP; END $$;"
        )
        cur.execute(
            "DO $$ DECLARE r RECORD; BEGIN "
            "FOR r IN SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='S' "
            "AND c.relname LIKE 'mem0%' LOOP "
            "EXECUTE format('GRANT ALL ON SEQUENCE public.%I TO mem0ai', r.relname); "
            "END LOOP; END $$;"
        )

        # Strip default grants for tables created by the main omni role in
        # the future (later migrations).
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{database_username}" '
            "IN SCHEMA public REVOKE ALL ON TABLES    FROM mem0ai"
        )
        cur.execute(
            f'ALTER DEFAULT PRIVILEGES FOR ROLE "{database_username}" '
            "IN SCHEMA public REVOKE ALL ON SEQUENCES FROM mem0ai"
        )

    logger.info("mem0ai role grants and revokes applied")
