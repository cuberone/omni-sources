"""Thin async httpx wrapper around the mem0 REST API."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MemoryClient:
    """Async client for the mem0 memory service.

    All methods are best-effort: failures are logged as warnings and never
    propagate to the caller — memory is non-critical infrastructure.
    """

    def __init__(self, base_url: str, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def search(self, query: str, user_id: str, limit: int = 5) -> list[str]:
        """Search for relevant memories for user_id given a query.

        Returns a list of memory strings, empty list on any failure.
        """
        url = f"{self._base_url}/v1/memories/search/"
        payload = {"query": query, "user_id": user_id, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return [item["memory"] for item in data.get("results", [])]
        except Exception as e:
            logger.warning(f"Memory search failed for user {user_id}: {e}")
            return []

    async def add(self, messages: list[dict[str, Any]], user_id: str) -> None:
        """Add a conversation turn to memory for user_id.

        Fire-and-forget: logs warnings on failure, never raises.
        """
        url = f"{self._base_url}/v1/memories/"
        payload = {"messages": messages, "user_id": user_id}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Memory add failed for user {user_id}: {e}")
