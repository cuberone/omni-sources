"""Unit tests for memory mode resolution logic."""
import pytest
from memory.mode import resolve_memory_mode


@pytest.mark.unit
class TestResolveMemoryMode:
    def test_user_override_wins_over_org_default(self):
        assert resolve_memory_mode(user_mode="chat", org_default="full") == "chat"

    def test_user_off_wins_over_org_full(self):
        assert resolve_memory_mode(user_mode="off", org_default="full") == "off"

    def test_none_user_falls_back_to_org_default(self):
        assert resolve_memory_mode(user_mode=None, org_default="chat") == "chat"

    def test_none_user_none_org_defaults_to_off(self):
        assert resolve_memory_mode(user_mode=None, org_default=None) == "off"

    def test_org_default_full_with_no_user_override(self):
        assert resolve_memory_mode(user_mode=None, org_default="full") == "full"

    def test_invalid_mode_treated_as_off(self):
        assert resolve_memory_mode(user_mode="unknown", org_default="chat") == "off"
