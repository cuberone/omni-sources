-- 088_add_memory_mode.sql
-- Memory feature schema setup:
--   1. `configuration` table for the org-wide memory_mode default
--   2. `user_preferences` table for per-user memory_mode override
--   3. Restricted `mem0ai` Postgres role + grants/revokes
--
-- The `mem0ai` role is created NOLOGIN; the AI service flips it to LOGIN
-- with the env-supplied password on first boot (advisory-locked so the N
-- uvicorn workers don't race on pg_authid). Role name is hardcoded — if
-- MEM0AI_DATABASE_USER is overridden, the operator creates that role
-- themselves with the same grants.

-- ---------------------------------------------------------------------------
-- configuration
-- ---------------------------------------------------------------------------

-- The configuration table was dropped unconditionally in migration 051.
-- Recreate it here (schema from migration 032; trigger renamed to match later conventions).
CREATE TABLE IF NOT EXISTS configuration (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_configuration_updated_at
    BEFORE UPDATE ON configuration
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

INSERT INTO configuration (key, value)
VALUES ('memory_mode_default', '{"mode": "off"}')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- user_preferences
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id CHAR(26) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);

CREATE OR REPLACE TRIGGER set_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Self-heal dev DBs that ran an earlier version of this migration which
-- added users.memory_mode directly: backfill survivors then drop the column.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'memory_mode'
    ) THEN
        EXECUTE $sql$
            INSERT INTO user_preferences (user_id, key, value)
            SELECT id, 'memory_mode', to_jsonb(memory_mode)
            FROM users WHERE memory_mode IS NOT NULL
            ON CONFLICT DO NOTHING
        $sql$;
        ALTER TABLE users DROP COLUMN memory_mode;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- mem0ai role
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mem0ai') THEN
        CREATE ROLE mem0ai NOLOGIN;
    END IF;
END$$;

-- Reassign any pre-existing mem0_* tables owned by another role. Guards
-- against dev DBs where a prior version of role_bootstrap.py created
-- the tables under the privileged role before fixing ownership.
DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'mem0%'
          AND tableowner <> 'mem0ai'
    LOOP
        EXECUTE format('ALTER TABLE public.%I OWNER TO mem0ai', rec.tablename);
    END LOOP;
END$$;

-- Revoke blanket access on omni's tables, sequences, and functions.
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM mem0ai;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mem0ai;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM mem0ai;

-- Grant connect + schema usage. Schema CREATE so mem0 can build its
-- own tables on first call.
GRANT USAGE, CREATE ON SCHEMA public TO mem0ai;

-- Restore mem0's access to its own tables (the blanket REVOKE above
-- stripped them too).
DO $$
DECLARE rec RECORD;
BEGIN
    FOR rec IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename LIKE 'mem0%'
    LOOP
        EXECUTE format('GRANT ALL ON TABLE public.%I TO mem0ai', rec.tablename);
    END LOOP;
    FOR rec IN
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'S'
          AND c.relname LIKE 'mem0%'
    LOOP
        EXECUTE format('GRANT ALL ON SEQUENCE public.%I TO mem0ai', rec.relname);
    END LOOP;
END$$;

-- Block future omni-owned tables from auto-granting access to mem0ai.
-- `current_user` is the migrator's role, which equals the public-schema
-- owner.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL ON TABLES    FROM mem0ai',
        current_user
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
        'REVOKE ALL ON SEQUENCES FROM mem0ai',
        current_user
    );
END$$;

-- GRANT CONNECT on the live database (name not known at file-write time).
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO mem0ai', current_database());
END$$;
