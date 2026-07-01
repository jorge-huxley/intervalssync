"""Tests for the secret-store wrapper.

The real flet-secure-storage service needs a running Flet page, so here we just
verify FletSecureStorage delegates correctly to an async storage object. A live
round-trip is verified by running the app, not in unit tests.
"""

from __future__ import annotations

import asyncio
import subprocess

from intervalssync.gui import secrets as secrets_module


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


class FakeMacOSKeychainStore(secrets_module.MacOSKeychainStore):
    def __init__(self, results):
        super().__init__(service="test.service")
        self.results = list(results)
        self.calls: list[tuple[str, ...]] = []

    def _run_security(self, *args):
        self.calls.append(args)
        return self.results.pop(0)


def security_result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["security"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_fletsecurestorage_delegates():
    store = secrets_module.FletSecureStorage(FakeSecureStorage())

    async def scenario():
        assert await store.get("k") is None
        await store.set("k", "secret")
        assert await store.get("k") == "secret"
        await store.delete("k")
        assert await store.get("k") is None

    asyncio.run(scenario())


def test_macos_keychain_store_uses_security_cli():
    store = FakeMacOSKeychainStore(
        [
            security_result(stdout="secret\n"),
            security_result(),
            security_result(),
        ]
    )

    async def scenario():
        assert await store.get("k") == "secret"
        await store.set("k", "new-secret")
        await store.delete("k")

    asyncio.run(scenario())

    assert store.calls == [
        (
            "find-generic-password",
            "-s",
            "test.service",
            "-a",
            "k",
            "-w",
        ),
        (
            "add-generic-password",
            "-U",
            "-s",
            "test.service",
            "-a",
            "k",
            "-w",
            "new-secret",
        ),
        (
            "delete-generic-password",
            "-s",
            "test.service",
            "-a",
            "k",
        ),
    ]


def test_macos_keychain_store_returns_none_for_missing_secret():
    store = FakeMacOSKeychainStore(
        [security_result(returncode=44, stderr="The specified item could not be found.")]
    )

    async def scenario():
        assert await store.get("missing") is None

    asyncio.run(scenario())


def test_macos_keychain_store_ignores_delete_for_missing_secret():
    store = FakeMacOSKeychainStore(
        [security_result(returncode=44, stderr="The specified item could not be found.")]
    )

    async def scenario():
        await store.delete("missing")

    asyncio.run(scenario())


def test_macos_keychain_store_raises_other_errors():
    store = FakeMacOSKeychainStore([security_result(returncode=1, stderr="boom")])

    async def scenario():
        try:
            await store.set("k", "secret")
        except RuntimeError as exc:
            assert "Could not save Keychain item 'k': boom" == str(exc)
        else:
            raise AssertionError("expected RuntimeError")

    asyncio.run(scenario())


def test_dropbox_refresh_token_key_is_declared():
    assert secrets_module.DROPBOX_REFRESH_TOKEN == "dropbox_refresh_token"
