"""Agent providers. Adding one means adding a module here and a line to PROVIDERS."""
from __future__ import annotations

import os

from .base import Provider
from .claude import Claude

PROVIDERS = {"claude": Claude}


def get(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        known = ", ".join(PROVIDERS)
        raise SystemExit(f"threadr: unknown provider '{name}' (known: {known})") from None


def enabled(only: str | None = None) -> list[Provider]:
    """Providers to search: --provider, else THREADR_PROVIDERS, else every installed one."""
    names = only or os.environ.get("THREADR_PROVIDERS", "")
    if names:
        return [get(n.strip()) for n in names.split(",") if n.strip()]
    return [p for p in (cls() for cls in PROVIDERS.values()) if p.available()]


def current() -> tuple | None:
    """(provider, session id) when running inside an agent session."""
    for cls in PROVIDERS.values():
        provider = cls()
        sid = provider.current_session()
        if sid:
            return provider, sid
    return None
