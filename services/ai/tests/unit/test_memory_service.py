"""Unit tests for the in-process MemoryService."""
from unittest.mock import MagicMock, patch

import pytest


_DB_CONFIG = {
    "host": "db", "port": 5432, "dbname": "omni",
    "user": "mem0ai", "password": "mem0ai",
    "collection_name": "mem0_memories_test",
}


def _service(memory=None):
    from memory.service import MemoryService
    mem = memory or MagicMock()
    mem.db.db_path = "/tmp/mem0_history_test.db"
    return MemoryService(mem, _DB_CONFIG), mem


@pytest.mark.unit
class TestAdd:
    @pytest.mark.asyncio
    async def test_add_empty_messages_returns_without_calling_mem0(self):
        svc, mem = _service()
        await svc.add(messages=[], user_id="u1")
        mem.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_flattens_list_content_to_text_only(self):
        svc, mem = _service()
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image", "url": "x"},
                {"type": "text", "text": "world"},
            ],
        }]
        await svc.add(messages=messages, user_id="u1")
        call_args = mem.add.call_args
        assert call_args.args[0] == [{"role": "user", "content": "hello world"}]
        assert call_args.kwargs == {"user_id": "u1"}

    @pytest.mark.asyncio
    async def test_add_drops_messages_that_collapse_to_empty(self):
        svc, mem = _service()
        messages = [
            {"role": "user", "content": [{"type": "image", "url": "x"}]},
            {"role": "assistant", "content": "reply"},
        ]
        await svc.add(messages=messages, user_id="u1")
        assert mem.add.call_args.args[0] == [{"role": "assistant", "content": "reply"}]

    @pytest.mark.asyncio
    async def test_add_noop_when_entire_batch_collapses(self):
        svc, mem = _service()
        await svc.add(
            messages=[{"role": "user", "content": [{"type": "image", "url": "x"}]}],
            user_id="u1",
        )
        mem.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_swallows_mem0_errors(self):
        svc, mem = _service()
        mem.add.side_effect = RuntimeError("mem0 down")
        await svc.add(messages=[{"role": "user", "content": "hi"}], user_id="u1")


@pytest.mark.unit
class TestSearch:
    @pytest.mark.asyncio
    async def test_search_wraps_user_id_into_filters(self):
        svc, mem = _service()
        mem.search.return_value = {"results": [{"memory": "a"}, {"memory": "b"}]}
        got = await svc.search(query="q", user_id="u1", limit=5)
        assert got == ["a", "b"]
        mem.search.assert_called_once_with(
            "q", top_k=5, filters={"user_id": "u1"}
        )

    @pytest.mark.asyncio
    async def test_search_wraps_bare_list_response(self):
        svc, mem = _service()
        mem.search.return_value = [{"memory": "x"}]
        got = await svc.search(query="q", user_id="u1", limit=3)
        assert got == ["x"]

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self):
        svc, mem = _service()
        mem.search.side_effect = RuntimeError("down")
        got = await svc.search(query="q", user_id="u1", limit=5)
        assert got == []


@pytest.mark.unit
class TestListAndDelete:
    @pytest.mark.asyncio
    async def test_list_normalises_dict_response(self):
        svc, mem = _service()
        mem.get_all.return_value = {"results": [{"id": "a", "memory": "m"}]}
        got = await svc.list(user_id="u1")
        assert got == [{"id": "a", "memory": "m"}]
        mem.get_all.assert_called_once_with(filters={"user_id": "u1"})

    @pytest.mark.asyncio
    async def test_list_normalises_bare_list(self):
        svc, mem = _service()
        mem.get_all.return_value = [{"id": "a"}]
        got = await svc.list(user_id="u1")
        assert got == [{"id": "a"}]

    @pytest.mark.asyncio
    async def test_list_returns_empty_on_error(self):
        svc, mem = _service()
        mem.get_all.side_effect = RuntimeError("down")
        assert await svc.list(user_id="u1") == []

    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        svc, mem = _service()
        assert await svc.delete(memory_id="m1") is True
        mem.delete.assert_called_once_with("m1")

    @pytest.mark.asyncio
    async def test_delete_returns_false_on_error(self):
        svc, mem = _service()
        mem.delete.side_effect = RuntimeError("down")
        assert await svc.delete(memory_id="m1") is False


@pytest.mark.unit
class TestDeleteAll:
    @pytest.mark.asyncio
    async def test_delete_all_clears_sqlite_buffer_and_purges_tables(self):
        svc, mem = _service()

        # Mock psycopg connection used by _purge_user_across_all_collections.
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [("mem0_memories_aaa",), ("mem0_memories_bbb",)]
        cur.rowcount = 3  # rows deleted per table
        conn.execute.side_effect = [cur, cur, cur]  # SELECT, DELETE aaa, DELETE bbb
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        sqlite_conn = MagicMock()
        sqlite_conn.__enter__ = MagicMock(return_value=sqlite_conn)
        sqlite_conn.__exit__ = MagicMock(return_value=False)

        with patch("memory.service.psycopg.connect", return_value=conn), \
             patch("memory.service.sqlite3.connect", return_value=sqlite_conn):
            total = await svc.delete_all(user_id="u1")

        mem.delete_all.assert_called_once_with(user_id="u1")
        sqlite_conn.execute.assert_called_once_with(
            "DELETE FROM messages WHERE session_scope = ?",
            ("user_id=u1",),
        )
        # SELECT + 2 DELETEs
        assert conn.execute.call_count == 3
        assert total == 6  # rowcount 3 × 2 tables

    @pytest.mark.asyncio
    async def test_delete_all_returns_zero_on_purge_failure(self):
        svc, mem = _service()
        sqlite_conn = MagicMock()
        sqlite_conn.__enter__ = MagicMock(return_value=sqlite_conn)
        sqlite_conn.__exit__ = MagicMock(return_value=False)

        with patch("memory.service.psycopg.connect", side_effect=RuntimeError("db down")), \
             patch("memory.service.sqlite3.connect", return_value=sqlite_conn):
            total = await svc.delete_all(user_id="u1")
        assert total == 0
