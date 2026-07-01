from __future__ import annotations

import flet as ft

from intervalssync.gui import app


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


def test_secure_storage_uses_login_keychain_on_macos():
    storage = app._secure_storage_for_platform(ft.PagePlatform.MACOS)

    assert storage.macos_options.uses_data_protection_keychain is False


def test_secure_storage_keeps_default_keychain_options_elsewhere():
    storage = app._secure_storage_for_platform(ft.PagePlatform.WINDOWS)

    assert storage.macos_options.uses_data_protection_keychain is True
