"""Tests for the secret-store wrapper.

The real flet-secure-storage service needs a running Flet page, so here we just
verify FletSecureStorage delegates correctly to an async storage object. A live
round-trip is verified by running the app, not in unit tests.
"""

from __future__ import annotations

import asyncio

from igpsync import secrets as secrets_module


class FakeSecureStorage:
    """Mimics the async get/set/remove of flet_secure_storage.SecureStorage."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = value

    async def remove(self, key):
        self.data.pop(key, None)


def test_fletsecurestorage_delegates():
    store = secrets_module.FletSecureStorage(FakeSecureStorage())

    async def scenario():
        assert await store.get("k") is None
        await store.set("k", "secret")
        assert await store.get("k") == "secret"
        await store.delete("k")
        assert await store.get("k") is None

    asyncio.run(scenario())
