"""Secure secret storage.

Secrets are kept in the operating system's native vault (Windows Credential
Manager, macOS/iOS Keychain, Android Keystore, Linux libsecret) via
`flet-secure-storage` — never in a plaintext file. The same backend works on
every platform Flet targets, so there is no per-OS branching.

`SecretStore` is the async seam between the GUI and storage. It's async because
`flet-secure-storage` talks to the Flutter side asynchronously.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from flet_secure_storage import SecureStorage

# Logical secret keys.
IGP_PASSWORD = "igp_password"
INTERVALS_API_KEY = "intervals_api_key"


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
