"""Lifetime sync stats, milestone celebrations, and support / partner UI."""

from __future__ import annotations

import asyncio
import math
import os
import random
from dataclasses import dataclass

import flet as ft

from ..i18n import is_chinese, t
from . import config as config_module
from . import theme

KOFI_URL = "https://ko-fi.com/jorge_huxley"
PARTNER_LOGO = "endurance_logo.png"

MILESTONES = [5, 25, 50, 100, 250, 500, 1000]

_MILESTONE_TITLE_KEYS: dict[int, str] = {
    5: "milestone.title.5",
    25: "milestone.title.25",
    50: "milestone.title.50",
    100: "milestone.title.100",
    250: "milestone.title.250",
    500: "milestone.title.500",
    1000: "milestone.title.1000",
}

_MILESTONE_MSG_KEYS: dict[int, str] = {
    5: "milestone.msg.5",
    25: "milestone.msg.25",
    50: "milestone.msg.50",
    100: "milestone.msg.100",
    250: "milestone.msg.250",
    500: "milestone.msg.500",
    1000: "milestone.msg.1000",
}

_CONFETTI_COLORS = (
    theme.ACCENT,
    theme.ACCENT_LIGHT,
    "#F2C94C",
    "#27AE60",
    "#2D9CDB",
    "#BB6BD9",
)

_CELEBRATION_WIDTH = 320
_CELEBRATION_HEIGHT = 340


@dataclass
class StatsCardRefs:
    number: ft.Ref[ft.Text]
    rank: ft.Ref[ft.Text]
    breakdown: ft.Ref[ft.Text]
    target: ft.Ref[ft.Text]
    remaining: ft.Ref[ft.Text]
    progress_bar: ft.Ref[ft.ProgressBar]


def total_uploads(config: config_module.AppConfig) -> int:
    return config_module.total_uploads(config)


def rank_for(total: int) -> str:
    if total <= 0:
        return t("rank.rookie")
    if total < 5:
        return t("rank.warmup")
    if total < 10:
        return t("rank.domestique")
    if total < 25:
        return t("rank.breakaway")
    if total < 50:
        return t("rank.climber")
    if total < 100:
        return t("rank.sprinter")
    if total < 250:
        return t("rank.century")
    return t("rank.grand_tourer")


def next_milestone(total: int) -> int | None:
    for milestone in MILESTONES:
        if total < milestone:
            return milestone
    return None


def _previous_milestone(total: int) -> int:
    previous = 0
    for milestone in MILESTONES:
        if total >= milestone:
            previous = milestone
        else:
            break
    return previous


def progress_fraction(total: int) -> float:
    nxt = next_milestone(total)
    if nxt is None:
        return 1.0
    prev = _previous_milestone(total)
    span = nxt - prev
    if span <= 0:
        return 0.0
    return (total - prev) / span


def milestone_title(milestone: int) -> str:
    key = _MILESTONE_TITLE_KEYS.get(milestone)
    if key is None:
        return t("milestone.title.fallback", n=milestone)
    return t(key)


def milestone_message(milestone: int) -> str:
    key = _MILESTONE_MSG_KEYS.get(milestone)
    if key is None:
        return t("milestone.msg.fallback", n=milestone)
    return t(key)


def _newly_crossed_milestone(old_total: int, new_total: int) -> int | None:
    crossed: int | None = None
    for milestone in MILESTONES:
        if old_total < milestone <= new_total:
            crossed = milestone
    return crossed


def record_uploads(
    config: config_module.AppConfig,
    *,
    activities: int = 0,
    workouts: int = 0,
) -> int | None:
    if activities <= 0 and workouts <= 0:
        return None

    old_total = total_uploads(config)
    config.lifetime_activities_uploaded += activities
    config.lifetime_workouts_uploaded += workouts
    new_total = total_uploads(config)

    milestone = _newly_crossed_milestone(old_total, new_total)
    if milestone is not None and milestone not in config.celebrated_milestones:
        config.celebrated_milestones.append(milestone)
        config_module.save(config)
        return milestone

    config_module.save(config)
    return None


def _breakdown_text(config: config_module.AppConfig) -> str:
    activities = config.lifetime_activities_uploaded
    workouts = config.lifetime_workouts_uploaded
    activity_word = t("stats.activity.one" if activities == 1 else "stats.activity.many")
    workout_word = t("stats.workout.one" if workouts == 1 else "stats.workout.many")
    return t(
        "stats.breakdown",
        activities=activities,
        activity_word=activity_word,
        workouts=workouts,
        workout_word=workout_word,
    )


def _target_text(total: int) -> str:
    nxt = next_milestone(total)
    if nxt is None:
        return t("stats.target.all_done")
    return t("stats.target.next", n=nxt)


def _remaining_text(total: int) -> str:
    nxt = next_milestone(total)
    if nxt is None:
        return t("stats.remaining.legend")
    remaining = nxt - total
    word = t("stats.sync.one" if remaining == 1 else "stats.sync.many")
    return t("stats.remaining", n=remaining, word=word)


def update_stats_display(
    page: ft.Page,
    config: config_module.AppConfig,
    refs: StatsCardRefs,
) -> None:
    total = total_uploads(config)
    if refs.number.current:
        refs.number.current.value = str(total)
    if refs.rank.current:
        refs.rank.current.value = rank_for(total).upper()
    if refs.breakdown.current:
        refs.breakdown.current.value = _breakdown_text(config)
    if refs.target.current:
        refs.target.current.value = _target_text(total)
    if refs.remaining.current:
        refs.remaining.current.value = _remaining_text(total)
    if refs.progress_bar.current:
        refs.progress_bar.current.value = progress_fraction(total)
    page.update()


def build_stats_card(
    page: ft.Page,
    config: config_module.AppConfig,
    refs: StatsCardRefs,
) -> ft.Container:
    colors = theme.palette(page)
    total = total_uploads(config)

    # Hero: a bike-computer-style metric readout — big number, tiny eyebrow.
    number = ft.Text(
        str(total),
        ref=refs.number,
        size=46,
        color=colors["accent"],
        weight=ft.FontWeight.BOLD,
        font_family=theme.display_font(),
    )
    eyebrow = ft.Text(
        t("stats.eyebrow"),
        size=10,
        weight=ft.FontWeight.W_700,
        color=colors["text_muted"],
        style=ft.TextStyle(letter_spacing=1.6),
    )
    hero = ft.Column(spacing=0, tight=True, controls=[number, eyebrow])

    rank_chip = ft.Container(
        content=ft.Text(
            rank_for(total).upper(),
            ref=refs.rank,
            size=11,
            weight=ft.FontWeight.W_700,
            color=colors["accent"],
            style=ft.TextStyle(letter_spacing=0.8),
        ),
        padding=ft.Padding(theme.SPACE_SM, 5, theme.SPACE_SM, 5),
        bgcolor=colors["accent_soft"],
        border_radius=999,
    )
    breakdown = ft.Text(
        _breakdown_text(config),
        ref=refs.breakdown,
        size=11,
        color=colors["text_muted"],
        text_align=ft.TextAlign.RIGHT,
    )
    meta = ft.Column(
        spacing=theme.SPACE_XS,
        horizontal_alignment=ft.CrossAxisAlignment.END,
        controls=[rank_chip, breakdown],
    )

    top_row = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[hero, meta],
    )

    target = ft.Text(
        _target_text(total),
        ref=refs.target,
        size=11,
        weight=ft.FontWeight.W_600,
        color=colors["text_muted"],
        font_family=theme.body_font_medium(),
    )
    remaining = ft.Text(
        _remaining_text(total),
        ref=refs.remaining,
        size=11,
        color=colors["text_muted"],
    )
    progress_header = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[target, remaining],
    )
    progress_bar = ft.ProgressBar(
        ref=refs.progress_bar,
        value=progress_fraction(total),
        color=colors["accent"],
        bgcolor=colors["surface_alt"],
        bar_height=6,
        border_radius=3,
    )
    progress = ft.Column(
        spacing=theme.SPACE_XS,
        controls=[progress_header, progress_bar],
    )

    async def on_partner_click(_: ft.ControlEvent) -> None:
        await show_partner_dialog(page)

    if is_chinese():
        support_btn: ft.Control = ft.TextButton(
            t("stats.kofi_button"),
            on_click=on_partner_click,
            style=ft.ButtonStyle(
                color=colors["text_muted"],
                padding=ft.Padding(0, 0, 0, 0),
            ),
        )
    else:
        support_btn = ft.TextButton(
            t("stats.kofi_button"),
            url=KOFI_URL,
            style=ft.ButtonStyle(
                color=colors["text_muted"],
                padding=ft.Padding(0, 0, 0, 0),
            ),
        )

    return ft.Container(
        content=ft.Column(
            spacing=theme.SPACE_MD,
            controls=[
                top_row,
                progress,
                support_btn,
            ],
        ),
        padding=theme.SPACE_LG,
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=theme.RADIUS_MD,
    )


async def show_kofi_dialog(page: ft.Page) -> None:
    """English Ko-fi support dialog (unchanged behavior)."""
    colors = theme.palette(page)

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
            title=theme.display_text(t("kofi.dialog.title"), size=22),
            content=ft.Text(
                t("kofi.dialog.body"),
                size=13,
                color=colors["text_muted"],
            ),
            actions=[
                ft.TextButton(t("kofi.dialog.not_now"), on_click=lambda _: page.pop_dialog()),
                ft.TextButton(t("kofi.dialog.support"), url=KOFI_URL),
            ],
        )
    )
    page.update()


async def show_partner_dialog(page: ft.Page) -> None:
    """Chinese Endurance Cycling partner intro (no external link)."""
    colors = theme.palette(page)

    # Two layers: app surface color under a transparent-bg logo (no white plate).
    logo = ft.Container(
        content=ft.Image(
            src=PARTNER_LOGO,
            width=220,
            fit=ft.BoxFit.CONTAIN,
        ),
        bgcolor=colors["surface"],
        padding=ft.Padding(theme.SPACE_MD, theme.SPACE_SM, theme.SPACE_MD, theme.SPACE_SM),
        border_radius=theme.RADIUS_SM,
        alignment=ft.Alignment.CENTER,
    )

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            bgcolor=colors["surface"],
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
            content=ft.Container(
                bgcolor=colors["surface"],
                content=ft.Column(
                    tight=True,
                    spacing=theme.SPACE_MD,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        logo,
                        theme.display_text(t("kofi.dialog.title"), size=22),
                        ft.Text(
                            t("partner.slogan"),
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=colors["text"],
                            text_align=ft.TextAlign.CENTER,
                            font_family=theme.body_font_medium(),
                        ),
                        ft.Text(
                            t("kofi.dialog.body"),
                            size=13,
                            color=colors["text_muted"],
                            text_align=ft.TextAlign.CENTER,
                            font_family=theme.body_font(),
                        ),
                    ],
                ),
            ),
            actions=[
                ft.FilledButton(
                    t("kofi.dialog.support"),
                    on_click=lambda _: page.pop_dialog(),
                ),
            ],
        )
    )
    page.update()


async def show_support_dialog(page: ft.Page) -> None:
    if is_chinese():
        await show_partner_dialog(page)
    else:
        await show_kofi_dialog(page)


def kofi_header_button(page: ft.Page) -> ft.IconButton:
    colors = theme.palette(page)

    async def on_click(_: ft.ControlEvent) -> None:
        await show_support_dialog(page)

    return ft.IconButton(
        icon=ft.Icons.DIRECTIONS_BIKE if is_chinese() else ft.Icons.LOCAL_CAFE_OUTLINED,
        tooltip=t("kofi.tooltip"),
        icon_color=colors["text_muted"],
        on_click=on_click,
    )


def _build_confetti() -> list[ft.Container]:
    """Small colored squares/circles that start near the top of the card."""
    particles: list[ft.Container] = []
    for _ in range(30):
        size = random.randint(6, 12)
        start_left = random.uniform(0, _CELEBRATION_WIDTH)
        duration = random.randint(950, 1500)
        particle = ft.Container(
            width=size,
            height=size,
            bgcolor=random.choice(_CONFETTI_COLORS),
            border_radius=size / 2 if random.random() > 0.5 else 2,
            left=start_left,
            top=random.uniform(-24, 8),
            opacity=1.0,
            rotate=ft.Rotate(0, alignment=ft.Alignment.CENTER),
            ignore_interactions=True,
            animate_position=ft.Animation(
                duration=ft.Duration(milliseconds=duration),
                curve=ft.AnimationCurve.EASE_IN,
            ),
            animate_opacity=ft.Animation(
                duration=ft.Duration(milliseconds=duration),
                curve=ft.AnimationCurve.EASE_IN,
            ),
            animate_rotation=ft.Animation(
                duration=ft.Duration(milliseconds=duration),
                curve=ft.AnimationCurve.LINEAR,
            ),
        )
        particle.data = {
            "left": start_left + random.uniform(-50, 50),
            "top": _CELEBRATION_HEIGHT + random.uniform(0, 60),
            "angle": random.uniform(-math.pi * 3, math.pi * 3),
        }
        particles.append(particle)
    return particles


async def _play_celebration(
    page: ft.Page,
    number_ref: ft.Ref[ft.Container],
    particles: list[ft.Container],
) -> None:
    await asyncio.sleep(0.05)
    if number_ref.current is not None:
        number_ref.current.scale = 1.0
        number_ref.current.opacity = 1.0
    for particle in particles:
        target = particle.data
        particle.left = target["left"]
        particle.top = target["top"]
        particle.opacity = 0.0
        particle.rotate = ft.Rotate(target["angle"], alignment=ft.Alignment.CENTER)
    try:
        page.update()
    except Exception:
        pass


async def show_milestone_dialog(page: ft.Page, milestone: int) -> None:
    colors = theme.palette(page)
    title = milestone_title(milestone)
    message = milestone_message(milestone)

    number_ref: ft.Ref[ft.Container] = ft.Ref()
    big_number = ft.Container(
        ref=number_ref,
        content=theme.display_text(
            str(milestone),
            size=76,
            color=colors["accent"],
            weight=ft.FontWeight.BOLD,
        ),
        alignment=ft.Alignment.CENTER,
        opacity=0.0,
        scale=0.5,
        animate_scale=ft.Animation(
            duration=ft.Duration(milliseconds=520),
            curve=ft.AnimationCurve.EASE_OUT_BACK,
        ),
        animate_opacity=ft.Animation(
            duration=ft.Duration(milliseconds=360),
            curve=ft.AnimationCurve.EASE_OUT,
        ),
    )

    content_column = ft.Column(
        tight=True,
        spacing=theme.SPACE_XS,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            big_number,
            ft.Text(
                t("celebration.syncs_completed"),
                size=11,
                weight=ft.FontWeight.W_600,
                color=colors["text_muted"],
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=theme.SPACE_SM),
            theme.display_text(title, size=24, color=colors["text"]),
            ft.Container(height=2),
            ft.Text(
                message,
                size=13,
                color=colors["text_muted"],
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=theme.SPACE_MD),
            ft.Text(
                t("celebration.kofi_line"),
                size=12,
                color=colors["text_muted"],
                text_align=ft.TextAlign.CENTER,
            ),
        ],
    )

    particles = _build_confetti()
    content = ft.Container(
        width=_CELEBRATION_WIDTH,
        height=_CELEBRATION_HEIGHT,
        content=ft.Stack(
            controls=[
                ft.Container(
                    width=_CELEBRATION_WIDTH,
                    height=_CELEBRATION_HEIGHT,
                    alignment=ft.Alignment.CENTER,
                    content=content_column,
                ),
                *particles,
            ],
        ),
    )

    async def on_partner_from_milestone(_: ft.ControlEvent) -> None:
        page.pop_dialog()
        await show_partner_dialog(page)

    if is_chinese():
        primary_action: ft.Control = ft.TextButton(
            t("celebration.buy_coffee"),
            on_click=on_partner_from_milestone,
        )
    else:
        primary_action = ft.TextButton(t("celebration.buy_coffee"), url=KOFI_URL)

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
            content=content,
            actions=[
                primary_action,
                ft.FilledButton(
                    t("celebration.keep_rolling"),
                    on_click=lambda _: page.pop_dialog(),
                ),
            ],
        )
    )
    page.update()

    page.run_task(_play_celebration, page, number_ref, particles)


# --- Dev-only milestone testing (INTERVALSSYNC_DEV_GAMIFICATION=1) ---


def dev_mode_enabled() -> bool:
    return os.environ.get("INTERVALSSYNC_DEV_GAMIFICATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def dev_reset_stats(config: config_module.AppConfig) -> None:
    config.lifetime_activities_uploaded = 0
    config.lifetime_workouts_uploaded = 0
    config.celebrated_milestones = []
    config.stats_seeded = True
    config_module.save(config)


def dev_set_total(config: config_module.AppConfig, total: int) -> None:
    total = max(0, total)
    config.lifetime_activities_uploaded = total
    config.lifetime_workouts_uploaded = 0
    config.celebrated_milestones = [milestone for milestone in MILESTONES if milestone <= total]
    config.stats_seeded = True
    config_module.save(config)


def dev_bump_and_maybe_celebrate(
    page: ft.Page,
    config: config_module.AppConfig,
    stats_refs: StatsCardRefs,
    *,
    activities: int = 0,
    workouts: int = 0,
) -> None:
    milestone = record_uploads(config, activities=activities, workouts=workouts)
    update_stats_display(page, config, stats_refs)
    if milestone is None:
        page.update()
        return

    async def _celebrate() -> None:
        await show_milestone_dialog(page, milestone)

    page.run_task(_celebrate)


def build_dev_milestone_panel(
    page: ft.Page,
    config: config_module.AppConfig,
    stats_refs: StatsCardRefs,
) -> ft.Container:
    colors = theme.palette(page)
    total_field = ft.TextField(
        label="Total transfers",
        value=str(total_uploads(config)),
        keyboard_type=ft.KeyboardType.NUMBER,
        width=140,
        dense=True,
    )

    def _refresh_total_field() -> None:
        total_field.value = str(total_uploads(config))

    def on_reset(_: ft.ControlEvent) -> None:
        dev_reset_stats(config)
        update_stats_display(page, config, stats_refs)
        _refresh_total_field()
        page.update()

    def on_bump(activities: int = 0, workouts: int = 0):
        def handler(_: ft.ControlEvent) -> None:
            dev_bump_and_maybe_celebrate(
                page,
                config,
                stats_refs,
                activities=activities,
                workouts=workouts,
            )
            _refresh_total_field()
            page.update()

        return handler

    def on_apply_total(_: ft.ControlEvent) -> None:
        try:
            total = int((total_field.value or "0").strip())
        except ValueError:
            return
        dev_set_total(config, total)
        update_stats_display(page, config, stats_refs)
        _refresh_total_field()
        page.update()

    def on_preview(milestone: int):
        async def handler(_: ft.ControlEvent) -> None:
            await show_milestone_dialog(page, milestone)

        return handler

    preview_buttons = [
        ft.TextButton(str(milestone), on_click=on_preview(milestone))
        for milestone in MILESTONES
    ]

    return ft.Container(
        content=ft.Column(
            spacing=theme.SPACE_SM,
            controls=[
                ft.Text(
                    "DEV milestone testing (INTERVALSSYNC_DEV_GAMIFICATION=1)",
                    size=11,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.ORANGE_400,
                ),
                ft.Row(
                    wrap=True,
                    spacing=theme.SPACE_SM,
                    controls=[
                        ft.OutlinedButton("+1 activity", on_click=on_bump(activities=1)),
                        ft.OutlinedButton("+1 workout", on_click=on_bump(workouts=1)),
                        ft.OutlinedButton("+5 transfers", on_click=on_bump(activities=5)),
                        ft.OutlinedButton("Reset stats", on_click=on_reset),
                    ],
                ),
                ft.Row(
                    spacing=theme.SPACE_SM,
                    controls=[
                        total_field,
                        ft.OutlinedButton("Set total", on_click=on_apply_total),
                    ],
                ),
                ft.Row(
                    wrap=True,
                    spacing=0,
                    controls=[
                        ft.Text("Preview popup:", size=11, color=colors["text_muted"]),
                        *preview_buttons,
                    ],
                ),
            ],
        ),
        padding=theme.SPACE_MD,
        bgcolor=colors["surface_alt"],
        border=ft.Border.all(1, ft.Colors.ORANGE_400),
        border_radius=theme.RADIUS_SM,
    )
