"""Secure secret storage.

Secrets are kept in the operating system's native vault (Windows Credential
Manager, macOS Keychain, Android Keystore, Linux libsecret) — never in a
plaintext file.

`SecretStore` is the async seam between the GUI and storage. Most platforms use
`flet-secure-storage`, while macOS uses the native `security` CLI to avoid
Flet's prebuilt desktop runner hitting Keychain entitlement errors.
"""

from __future__ import annotations

import asyncio
import subprocess
from abc import ABC, abstractmethod

from flet_secure_storage import SecureStorage

# Logical secret keys.
IGP_PASSWORD = "igp_password"
BRYTON_PASSWORD = "bryton_password"
INTERVALS_API_KEY = "intervals_api_key"
DROPBOX_REFRESH_TOKEN = "dropbox_refresh_token"
MACOS_KEYCHAIN_SERVICE = "io.github.jorgehuxley.intervalssync"


class SecretStore(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abstractmethod
    async def set(self, key: str, value: str) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...


class FletSecureStorage(SecretStore):
    """Stores secrets in the OS-native vault via a flet-secure-storage service.

    The `SecureStorage` service must already be registered on the page
    (``page.services.append(storage)``) before use.
    """

    def __init__(self, storage: SecureStorage) -> None:
        self._storage = storage

    async def get(self, key: str) -> str | None:
        return await self._storage.get(key)

    async def set(self, key: str, value: str) -> None:
        await self._storage.set(key, value)

    async def delete(self, key: str) -> None:
        await self._storage.remove(key)


class MacOSKeychainStore(SecretStore):
    """Stores secrets in the user's macOS login Keychain."""

    def __init__(self, service: str = MACOS_KEYCHAIN_SERVICE) -> None:
        self._service = service

    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_sync, key)

    async def set(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._set_sync, key, value)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_sync, key)

    def _get_sync(self, key: str) -> str | None:
        result = self._run_security(
            "find-generic-password",
            "-s",
            self._service,
            "-a",
            key,
            "-w",
        )
        if result.returncode == 0:
            return result.stdout.removesuffix("\n")
        if _is_missing_keychain_item(result):
            return None
        raise _keychain_error("read", key, result)

    def _set_sync(self, key: str, value: str) -> None:
        result = self._run_security(
            "add-generic-password",
            "-U",
            "-s",
            self._service,
            "-a",
            key,
            "-w",
            value,
        )
        if result.returncode != 0:
            raise _keychain_error("save", key, result)

    def _delete_sync(self, key: str) -> None:
        result = self._run_security(
            "delete-generic-password",
            "-s",
            self._service,
            "-a",
            key,
        )
        if result.returncode == 0 or _is_missing_keychain_item(result):
            return
        raise _keychain_error("delete", key, result)

    def _run_security(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["security", *args],
            capture_output=True,
            check=False,
            text=True,
        )


def _is_missing_keychain_item(result: subprocess.CompletedProcess[str]) -> bool:
    output = f"{result.stdout}\n{result.stderr}".lower()
    return result.returncode == 44 or "could not be found" in output


def _keychain_error(
    action: str,
    key: str,
    result: subprocess.CompletedProcess[str],
) -> RuntimeError:
    detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
    return RuntimeError(f"Could not {action} Keychain item {key!r}: {detail}")
