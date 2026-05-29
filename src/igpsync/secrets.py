"""Secure secret storage.

Secrets are kept in the operating system's native credential vault (Windows
Credential Manager, macOS Keychain, Linux Secret Service) via `keyring` — never
in a plaintext file.

`SecretStore` is the seam for portability: desktop keyring backends do not exist
in a Flet Android/iOS build, so a future `FletSecureStorage` backend (platform
Keystore/Keychain) can be dropped in here without touching core or UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import keyring

SERVICE_NAME = "igpsport-intervals"

# Logical secret keys used across the app.
IGP_PASSWORD = "igp_password"
INTERVALS_API_KEY = "intervals_api_key"


class SecretStore(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class KeyringSecretStore(SecretStore):
    """Stores secrets in the OS-native vault keyed by (SERVICE_NAME, key)."""

    def __init__(self, service_name: str = SERVICE_NAME) -> None:
        self.service_name = service_name

    def get(self, key: str) -> str | None:
        return keyring.get_password(self.service_name, key)

    def set(self, key: str, value: str) -> None:
        keyring.set_password(self.service_name, key, value)

    def delete(self, key: str) -> None:
        try:
            keyring.delete_password(self.service_name, key)
        except keyring.errors.PasswordDeleteError:
            # Already absent — nothing to do.
            pass
