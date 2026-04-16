"""Unit tests for MemoryClient."""
import pytest
import httpx
import respx
from memory.client import MemoryClient


@pytest.mark.unit
class TestMemoryClient:
    @pytest.fixture
    def client(self):
        return MemoryClient(base_url="http://memory:8888")

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_returns_facts(self, client):
        respx.post("http://memory:8888/v1/memories/search/").mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"memory": "User prefers bullet points"}]},
            )
        )
        facts = await client.search(query="formatting preferences", user_id="u1", limit=5)
        assert facts == ["User prefers bullet points"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_returns_empty_on_error(self, client):
        respx.post("http://memory:8888/v1/memories/search/").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )
        facts = await client.search(query="anything", user_id="u1", limit=5)
        assert facts == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_sends_messages_and_user_id(self, client):
        route = respx.post("http://memory:8888/v1/memories/").mock(
            return_value=httpx.Response(200, json={"id": "m1"})
        )
        messages = [
            {"role": "user", "content": "I like concise answers"},
            {"role": "assistant", "content": "Noted!"},
        ]
        await client.add(messages=messages, user_id="u1")
        assert route.called
        body = route.calls[0].request.read()
        import json
        payload = json.loads(body)
        assert payload["user_id"] == "u1"
        assert payload["messages"] == messages

    @respx.mock
    @pytest.mark.asyncio
    async def test_add_does_not_raise_on_error(self, client):
        respx.post("http://memory:8888/v1/memories/").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )
        await client.add(
            messages=[{"role": "user", "content": "test"}], user_id="u1"
        )
