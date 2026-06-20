"""Lifetime sync stats, milestone celebrations, and Ko-fi support UI."""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from . import config as config_module
from . import theme

KOFI_URL = "https://ko-fi.com/jorge_huxley"

MILESTONES = [1, 5, 10, 25, 50, 100, 250, 500, 1000]

_MILESTONE_TITLES: dict[int, str] = {
    1: "First transfer!",
    5: "Domestique status!",
    10: "Breakaway!",
    25: "Quarter century!",
    50: "Half century!",
    100: "Century!",
    250: "Grand tour stage!",
    500: "Monument ride!",
    1000: "Legend status!",
}


@dataclass
class StatsCardRefs:
    headline: ft.Ref[ft.Text]
    breakdown: ft.Ref[ft.Text]
    progress_label: ft.Ref[ft.Text]
    progress_bar: ft.Ref[ft.ProgressBar]


def total_uploads(config: config_module.AppConfig) -> int:
    return config_module.total_uploads(config)


def rank_for(total: int) -> str:
    if total <= 0:
        return "Rookie"
    if total < 5:
        return "Warm-up lap"
    if total < 10:
        return "Domestique"
    if total < 25:
        return "Breakaway"
    if total < 50:
        return "Climber"
    if total < 100:
        return "Sprinter"
    if total < 250:
        return "Century rider"
    return "Grand tourer"


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
    return _MILESTONE_TITLES.get(milestone, f"{milestone} transfers!")


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


def _headline_text(config: config_module.AppConfig) -> str:
    total = total_uploads(config)
    rank = rank_for(total)
    transfer_word = "transfer" if total == 1 else "transfers"
    return f"{rank} · {total} {transfer_word}"


def _breakdown_text(config: config_module.AppConfig) -> str:
    activities = config.lifetime_activities_uploaded
    workouts = config.lifetime_workouts_uploaded
    activity_word = "activity" if activities == 1 else "activities"
    workout_word = "workout" if workouts == 1 else "workouts"
    return f"{activities} {activity_word} · {workouts} {workout_word}"


def _progress_label_text(total: int) -> str:
    nxt = next_milestone(total)
    if nxt is None:
        return "All milestones reached — you're a legend"
    remaining = nxt - total
    transfer_word = "transfer" if remaining == 1 else "transfers"
    return f"{remaining} {transfer_word} to next milestone"


def update_stats_display(
    page: ft.Page,
    config: config_module.AppConfig,
    refs: StatsCardRefs,
) -> None:
    total = total_uploads(config)
    if refs.headline.current:
        refs.headline.current.value = _headline_text(config)
    if refs.breakdown.current:
        refs.breakdown.current.value = _breakdown_text(config)
    if refs.progress_label.current:
        refs.progress_label.current.value = _progress_label_text(total)
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

    headline = ft.Text(
        _headline_text(config),
        ref=refs.headline,
        size=15,
        weight=ft.FontWeight.W_600,
        font_family=f"{theme.FONT_BODY}Medium",
        color=colors["text"],
    )
    breakdown = ft.Text(
        _breakdown_text(config),
        ref=refs.breakdown,
        size=12,
        color=colors["text_muted"],
    )
    progress_label = ft.Text(
        _progress_label_text(total),
        ref=refs.progress_label,
        size=11,
        color=colors["text_muted"],
    )
    progress_bar = ft.ProgressBar(
        ref=refs.progress_bar,
        value=progress_fraction(total),
        color=colors["accent"],
        bgcolor=colors["surface_alt"],
        bar_height=4,
        border_radius=2,
    )

    return ft.Container(
        content=ft.Column(
            spacing=theme.SPACE_SM,
            controls=[
                headline,
                breakdown,
                progress_label,
                progress_bar,
                ft.TextButton(
                    "Saved you time? Buy me a coffee",
                    url=KOFI_URL,
                    style=ft.ButtonStyle(
                        color=colors["text_muted"],
                        padding=ft.Padding(0, 0, 0, 0),
                    ),
                ),
            ],
        ),
        padding=theme.SPACE_LG,
        bgcolor=colors["surface"],
        border=ft.Border.all(1, colors["border"]),
        border_radius=theme.RADIUS_MD,
    )


def kofi_header_button(page: ft.Page) -> ft.IconButton:
    colors = theme.palette(page)
    return ft.IconButton(
        icon=ft.Icons.LOCAL_CAFE_OUTLINED,
        tooltip="Support on Ko-fi",
        icon_color=colors["text_muted"],
        url=KOFI_URL,
    )


async def show_milestone_dialog(page: ft.Page, milestone: int) -> None:
    colors = theme.palette(page)
    title = milestone_title(milestone)

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            shape=ft.RoundedRectangleBorder(radius=theme.RADIUS_MD),
            title=theme.display_text(title, size=22),
            content=ft.Column(
                tight=True,
                spacing=theme.SPACE_SM,
                controls=[
                    ft.Text(
                        f"You've synced {milestone} activities and workouts with Intervals Sync. "
                        "Nice work keeping your training data flowing.",
                        size=13,
                        color=colors["text_muted"],
                    ),
                    ft.Text(
                        "If this app saves you time, consider supporting development on Ko-fi.",
                        size=13,
                        color=colors["text_muted"],
                    ),
                ],
            ),
            actions=[
                ft.TextButton("Support on Ko-fi", url=KOFI_URL),
                ft.TextButton("Keep rolling", on_click=lambda _: page.pop_dialog()),
            ],
        )
    )
    page.update()
