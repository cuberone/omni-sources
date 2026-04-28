"""Unit tests for sync_mem0ai_password.

The function runs at AI startup; schema-level setup happens once via
migration 085 and is exercised by the integration tests, not here. We
patch psycopg and assert the right statements run.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestSyncMem0aiPassword:
    def _fake_conn(self, alter_stmt: str = "ALTER ROLE mem0ai WITH LOGIN PASSWORD 'pw'"):
        conn = MagicMock()
        cur = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.__enter__.return_value = cur
        # Single fetchone for the `SELECT format(...)` round-trip that
        # returns the quoted ALTER ROLE statement.
        cur.fetchone.side_effect = [(alter_stmt,)]
        return conn, cur

    def test_alters_role_with_advisory_lock(self):
        from memory.role_bootstrap import sync_mem0ai_password

        conn, cur = self._fake_conn()
        with patch("memory.role_bootstrap.psycopg.connect", return_value=conn):
            sync_mem0ai_password(
                dsn="postgresql://omni:pw@db/omni",
                mem0ai_password="secret",
            )

        stmts = [call.args[0] for call in cur.execute.call_args_list]
        # First statement must acquire the advisory lock; ALTER ROLE comes after.
        assert stmts[0].startswith("SELECT pg_advisory_lock")
        assert any("ALTER ROLE mem0ai" in s for s in stmts)

    def test_uses_custom_role_name(self):
        from memory.role_bootstrap import sync_mem0ai_password

        conn, cur = self._fake_conn(
            alter_stmt="ALTER ROLE custom WITH LOGIN PASSWORD 'pw'"
        )
        with patch("memory.role_bootstrap.psycopg.connect", return_value=conn):
            sync_mem0ai_password(
                dsn="postgresql://omni:pw@db/omni",
                mem0ai_password="secret",
                role_name="custom",
            )

        stmts = " ".join(call.args[0] for call in cur.execute.call_args_list)
        assert "ALTER ROLE custom WITH LOGIN" in stmts

    def test_raises_when_password_missing(self):
        from memory.role_bootstrap import sync_mem0ai_password

        with pytest.raises(ValueError, match="MEM0AI_DATABASE_ROLE_PASSWORD"):
            sync_mem0ai_password(
                dsn="postgresql://omni:pw@db/omni",
                mem0ai_password=None,
            )

    def test_raises_on_non_identifier_role_name(self):
        from memory.role_bootstrap import sync_mem0ai_password

        with pytest.raises(ValueError, match="Invalid mem0ai role name"):
            sync_mem0ai_password(
                dsn="postgresql://omni:pw@db/omni",
                mem0ai_password="pw",
                role_name="role; DROP TABLE users",
            )
