"""Shared visual tokens and layout helpers for the Flet GUI."""

from __future__ import annotations

import flet as ft

# Palette — asphalt neutrals + signal-orange accent (bike-computer LED, not Material indigo).
ACCENT = "#D94E1F"
ACCENT_LIGHT = "#FF7A45"
ACCENT_SOFT = "#FFF0E8"
ACCENT_SOFT_DARK = "#2A1810"

BG_LIGHT = "#F6F7F9"
SURFACE_LIGHT = "#FFFFFF"
SURFACE_ALT_LIGHT = "#EEF0F4"
BORDER_LIGHT = "#DDE1E8"
TEXT_LIGHT = "#12151A"
TEXT_MUTED_LIGHT = "#5C6570"

BG_DARK = "#0C0E12"
SURFACE_DARK = "#161A21"
SURFACE_ALT_DARK = "#1E232C"
BORDER_DARK = "#2A3039"
TEXT_DARK = "#F2F4F7"
TEXT_MUTED_DARK = "#8B95A3"

FONT_BODY = "DMSans"
FONT_DISPLAY = "Outfit"

RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 20

SPACE_XS = 6
SPACE_SM = 10
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32


_MOBILE_PLATFORMS = {
    ft.PagePlatform.ANDROID,
    ft.PagePlatform.ANDROID_TV,
    ft.PagePlatform.IOS,
}


def is_mobile(page: ft.Page) -> bool:
    return page.platform in _MOBILE_PLATFORMS


def is_dark(page: ft.Page) -> bool:
    mode = page.theme_mode
    if mode == ft.ThemeMode.DARK:
        return True
    if mode == ft.ThemeMode.LIGHT:
        return False
    return page.platform_brightness == ft.Brightness.DARK


def palette(page: ft.Page) -> dict[str, str]:
    dark = is_dark(page)
    return {
        "bg": BG_DARK if dark else BG_LIGHT,
        "surface": SURFACE_DARK if dark else SURFACE_LIGHT,
        "surface_alt": SURFACE_ALT_DARK if dark else SURFACE_ALT_LIGHT,
        "border": BORDER_DARK if dark else BORDER_LIGHT,
        "text": TEXT_DARK if dark else TEXT_LIGHT,
        "text_muted": TEXT_MUTED_DARK if dark else TEXT_MUTED_LIGHT,
        "accent": ACCENT_LIGHT if dark else ACCENT,
        "accent_soft": ACCENT_SOFT_DARK if dark else ACCENT_SOFT,
    }


def apply_page_theme(page: ft.Page) -> None:
    page.fonts = {
        FONT_BODY: (
            "https://github.com/googlefonts/dm-fonts/raw/main/Sans/fonts/ttf/"
            "DMSans-Regular.ttf"
        ),
        f"{FONT_BODY}Medium": (
            "https://github.com/googlefonts/dm-fonts/raw/main/Sans/fonts/ttf/"
            "DMSans-Medium.ttf"
        ),
        FONT_DISPLAY: (
            "https://github.com/googlefonts/outfit/raw/main/fonts/ttf/"
            "Outfit-SemiBold.ttf"
        ),
    }

    scheme = ft.ColorScheme(
        primary=ACCENT,
        on_primary="#FFFFFF",
        primary_container=ACCENT_SOFT,
        on_primary_container="#5C1F08",
        secondary="#3D4654",
        on_secondary="#FFFFFF",
        surface=SURFACE_LIGHT,
        on_surface=TEXT_LIGHT,
        on_surface_variant=TEXT_MUTED_LIGHT,
        outline=BORDER_LIGHT,
        surface_container_lowest=BG_LIGHT,
        surface_container_low=BG_LIGHT,
        surface_container=SURFACE_ALT_LIGHT,
        surface_container_high=SURFACE_ALT_LIGHT,
        surface_container_highest=SURFACE_LIGHT,
    )
    scheme_dark = ft.ColorScheme(
        primary=ACCENT_LIGHT,
        on_primary="#2A1208",
        primary_container=ACCENT_SOFT_DARK,
        on_primary_container="#FFD6C2",
        secondary="#A8B0BC",
        on_secondary="#1A1E26",
        surface=SURFACE_DARK,
        on_surface=TEXT_DARK,
        on_surface_variant=TEXT_MUTED_DARK,
        outline=BORDER_DARK,
        surface_container_lowest=BG_DARK,
        surface_container_low=BG_DARK,
        surface_container=SURFACE_ALT_DARK,
        surface_container_high=SURFACE_ALT_DARK,
        surface_container_highest=SURFACE_DARK,
    )

    page.theme = ft.Theme(
        color_scheme=scheme,
        font_family=FONT_BODY,
        use_material3=True,
    )
    page.dark_theme = ft.Theme(
        color_scheme=scheme_dark,
        font_family=FONT_BODY,
        use_material3=True,
    )


def display_text(
    text: str,
    *,
    size: int = 28,
    color: str | None = None,
    weight: ft.FontWeight | None = None,
) -> ft.Text:
    return ft.Text(
        text,
        size=size,
        color=color,
        weight=weight,
        font_family=FONT_DISPLAY,
    )


def muted_text(text: str, page: ft.Page, *, size: int = 14) -> ft.Text:
    colors = palette(page)
    return ft.Text(text, size=size, color=colors["text_muted"])


def section_label(text: str, page: ft.Page) -> ft.Text:
    colors = palette(page)
    return ft.Text(
        text,
        size=11,
        weight=ft.FontWeight.W_600,
        color=colors["text_muted"],
        font_family=f"{FONT_BODY}Medium",
    )


def surface_card(
    page: ft.Page,
    content: ft.Control,
    *,
    padding: int = SPACE_LG,
    expand: bool = False,
) -> ft.Container:
    colors = palette(page)
    return ft.Container(
        content=content,
        padding=padding,
        expand=expand,
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=RADIUS_MD,
        shadow=ft.BoxShadow(
            spread_radius=0,
            blur_radius=18,
            color=ft.Colors.with_opacity(0.06, ft.Colors.BLACK),
            offset=ft.Offset(0, 4),
        ),
    )


def settings_section(
    page: ft.Page,
    title: str,
    *controls: ft.Control,
    subtitle: str | None = None,
) -> ft.Container:
    colors = palette(page)
    header: list[ft.Control] = [section_label(title, page)]
    if subtitle:
        header.append(
            ft.Text(subtitle, size=13, color=colors["text_muted"])
        )
    header.append(ft.Container(height=SPACE_SM))
    # Tighter side padding on phones so fields/helpers get more horizontal room.
    side = SPACE_MD if is_mobile(page) else SPACE_LG
    return ft.Container(
        content=ft.Column(
            spacing=SPACE_MD,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[*header, *controls],
        ),
        padding=ft.Padding(side, SPACE_LG, side, SPACE_LG),
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=RADIUS_MD,
    )
