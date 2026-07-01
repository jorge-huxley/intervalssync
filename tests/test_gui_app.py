from __future__ import annotations

import flet as ft

from intervalssync.gui import app
from intervalssync.gui import secrets as secrets_module


def test_permission_handler_skips_unsupported_desktop_platforms():
    assert not app._supports_permission_handler(ft.PagePlatform.MACOS)
    assert not app._supports_permission_handler(ft.PagePlatform.LINUX)


def test_permission_handler_allows_supported_platforms():
    assert app._supports_permission_handler(ft.PagePlatform.ANDROID)
    assert app._supports_permission_handler(ft.PagePlatform.IOS)
    assert app._supports_permission_handler(ft.PagePlatform.WINDOWS)

    web = getattr(ft.PagePlatform, "WEB", None)
    if web is not None:
        assert app._supports_permission_handler(web)


def test_secret_store_uses_native_keychain_on_macos():
    store, storage = app._secret_store_for_platform(ft.PagePlatform.MACOS)

    assert isinstance(store, secrets_module.MacOSKeychainStore)
    assert storage is None


def test_secret_store_uses_flet_secure_storage_elsewhere():
    store, storage = app._secret_store_for_platform(ft.PagePlatform.WINDOWS)

    assert isinstance(store, secrets_module.FletSecureStorage)
    assert storage is not None
