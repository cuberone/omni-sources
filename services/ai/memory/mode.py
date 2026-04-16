"""Memory mode resolution: effective mode = user override ?? org default ?? 'off'."""

VALID_MODES = {"off", "chat", "full"}


def resolve_memory_mode(
    user_mode: str | None,
    org_default: str | None,
) -> str:
    """Return the effective memory mode for a request.

    Priority:
      1. user_mode (explicit user preference, may be None = defer to org)
      2. org_default (admin-configured org default, may be None)
      3. 'off' (hard factory default)

    Any value outside {'off', 'chat', 'full'} is treated as 'off'.
    """
    for candidate in (user_mode, org_default):
        if candidate is not None:
            return candidate if candidate in VALID_MODES else "off"
    return "off"
