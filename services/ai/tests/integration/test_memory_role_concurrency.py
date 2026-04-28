"""Concurrent sync_mem0ai_password against a real Postgres.

Two threads call the function in parallel; the advisory lock serializes
them, so neither hits `tuple concurrently updated` on pg_authid.
"""
import threading

import pytest


@pytest.mark.integration
def test_concurrent_password_sync_does_not_race(initialized_db):
    """Migration 085 creates the role; both threads then sync the password."""
    from memory.role_bootstrap import sync_mem0ai_password
    from tests.conftest import _get_postgres_url

    dsn = _get_postgres_url(initialized_db)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def run(password: str) -> None:
        try:
            barrier.wait(timeout=5)
            sync_mem0ai_password(dsn=dsn, mem0ai_password=password)
        except BaseException as e:
            errors.append(e)

    t1 = threading.Thread(target=run, args=("first-pw-value",))
    t2 = threading.Thread(target=run, args=("second-pw-value",))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"sync raced and failed: {errors}"
    assert not t1.is_alive() and not t2.is_alive()
