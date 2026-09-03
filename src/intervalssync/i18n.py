"""Lightweight en/zh UI strings for the GUI and sync progress log.

CLI stays English. Missing keys fall back to English.
"""

from __future__ import annotations

import locale
import os
import sys
from pathlib import Path
from typing import Literal

Language = Literal["en", "zh"]

_VALID: frozenset[str] = frozenset({"en", "zh"})

# Windows LANG_* primary language ID for Chinese.
_WIN_LANG_CHINESE = 0x04

_current: Language = "en"

# fmt: off
_STRINGS: dict[str, dict[Language, str]] = {
    # --- App shell ---
    "app.title": {"en": "Intervals Sync", "zh": "Intervals Sync"},
    "header.subtitle": {
        "en": "iGPSPORT · Bryton · intervals.icu",
        "zh": "iGPSPORT · Bryton · intervals.icu",
    },
    "nav.sync": {"en": "Sync", "zh": "同步"},
    "nav.settings": {"en": "Settings", "zh": "设置"},
    "about.tooltip": {"en": "About", "zh": "关于"},
    "about.title": {"en": "About", "zh": "关于"},
    "about.version": {"en": "Version {version}", "zh": "版本 {version}"},
    "about.description": {
        "en": "Sync rides and planned workouts between iGPSPORT, Bryton Active, and intervals.icu.",
        "zh": "在 iGPSPORT、Bryton Active 与 intervals.icu 之间同步骑行活动与训练计划。",
    },
    "about.check_updates": {"en": "Check for updates", "zh": "检查更新"},
    "about.github": {"en": "GitHub", "zh": "GitHub"},
    "about.close": {"en": "Close", "zh": "关闭"},
    "update.available": {"en": "Update available: v{latest}", "zh": "发现新版本：v{latest}"},
    "update.action": {"en": "View", "zh": "查看"},
    "update.latest": {"en": "You're on the latest version.", "zh": "已是最新版本。"},

    # --- Settings ---
    "settings.page.title": {"en": "Settings", "zh": "设置"},
    "settings.page.subtitle": {
        "en": "Credentials are stored in your operating system's secure vault, never in a plain file.",
        "zh": "凭据保存在操作系统安全保险库中，不会以明文文件存储。",
    },
    "settings.section.language": {"en": "Language", "zh": "语言"},
    "settings.section.language.subtitle": {
        "en": "Choose the interface language.",
        "zh": "选择界面语言。",
    },
    "settings.language.label": {"en": "Interface language", "zh": "界面语言"},
    "settings.language.en": {"en": "English", "zh": "English"},
    "settings.language.zh": {"en": "简体中文", "zh": "简体中文"},
    "settings.section.accounts": {"en": "Accounts", "zh": "账户"},
    "settings.section.accounts.subtitle": {
        "en": "Enable sources and sign in to each service.",
        "zh": "启用数据源并登录各服务。",
    },
    "settings.section.sync_behavior": {"en": "Sync behavior", "zh": "同步行为"},
    "settings.save": {"en": "Save settings", "zh": "保存设置"},
    "settings.enable.igpsport": {"en": "Enable iGPSPORT", "zh": "启用 iGPSPORT"},
    "settings.igp.region": {"en": "iGPSPORT region", "zh": "iGPSPORT 区域"},
    "settings.igp.region.international": {"en": "International", "zh": "国际版"},
    "settings.igp.region.china": {"en": "China", "zh": "中国区"},
    "settings.igp.region.helper": {
        "en": "Use China if your account logs in at app.igpsport.cn",
        "zh": "若账号在 app.igpsport.cn 登录，请选择中国区",
    },
    "settings.igp.user.email": {"en": "iGPSPORT email", "zh": "iGPSPORT 邮箱"},
    "settings.igp.user.phone": {"en": "iGPSPORT phone number", "zh": "iGPSPORT 手机号"},
    "settings.igp.password": {"en": "iGPSPORT password", "zh": "iGPSPORT 密码"},
    "settings.enable.bryton": {"en": "Enable Bryton Active", "zh": "启用 Bryton Active"},
    "settings.bryton.email": {"en": "Bryton Active email", "zh": "Bryton Active 邮箱"},
    "settings.bryton.password": {"en": "Bryton Active password", "zh": "Bryton Active 密码"},
    "settings.intervals.api_key": {"en": "intervals.icu API key", "zh": "intervals.icu API 密钥"},
    "settings.intervals.api_key.helper": {
        "en": "Tap the i icon for a step-by-step guide.",
        "zh": "点旁边的小 i，按步骤找密钥。",
    },
    "settings.intervals.api_key.help.tooltip": {
        "en": "How to get your API key",
        "zh": "如何获取 API 密钥",
    },
    "settings.intervals.api_key.help.title": {
        "en": "How to get your intervals.icu API key",
        "zh": "怎么拿到 intervals.icu 的 API 密钥",
    },
    "settings.intervals.api_key.help.step1": {
        "en": "1. Open your phone or computer browser.",
        "zh": "1. 打开手机或电脑上的浏览器。",
    },
    "settings.intervals.api_key.help.step2": {
        "en": "2. Go to the website intervals.icu and sign in with your account.",
        "zh": "2. 打开网址 intervals.icu，用你的账号登录。",
    },
    "settings.intervals.api_key.help.step3": {
        "en": "3. After login, open Settings (usually via your profile picture or name).",
        "zh": "3. 登录后，点你的头像或名字，进入「设置 / Settings」。",
    },
    "settings.intervals.api_key.help.step4": {
        "en": "4. Scroll down the Settings page until you see “Developer Settings”.",
        "zh": "4. 在设置页一直往下滚，找到「Developer Settings / 开发者设置」。",
    },
    "settings.intervals.api_key.help.step5": {
        "en": "5. In that section, find “API Key”. If there isn’t one yet, create or show it.",
        "zh": "5. 在这一块里找到「API Key」。如果还没有，就点创建或显示密钥。",
    },
    "settings.intervals.api_key.help.step6": {
        "en": "6. Copy that long string of letters/numbers.",
        "zh": "6. 把那一长串字母数字复制下来。",
    },
    "settings.intervals.api_key.help.step7": {
        "en": "7. Come back here and paste it into the “intervals.icu API key” box, then save settings.",
        "zh": "7. 回到本软件，粘贴到「intervals.icu API 密钥」输入框，再点保存设置。",
    },
    "settings.intervals.api_key.help.note": {
        "en": "Tip: treat the key like a password. Don’t share it with strangers.",
        "zh": "小提示：密钥跟密码一样重要，别发给陌生人。",
    },
    "settings.intervals.api_key.help.close": {"en": "Got it", "zh": "知道了"},
    "settings.max_activities": {"en": "Activities to sync", "zh": "同步活动数量"},
    "settings.max_activities.helper": {
        "en": "Number of recent activities to sync on each run",
        "zh": "每次同步最近多少条活动",
    },
    "settings.workout_days": {"en": "Workout upload window (days)", "zh": "训练计划上传天数"},
    "settings.workout_days.helper": {
        "en": "Planned workouts from intervals.icu to upload to iGPSPORT and/or Bryton; 1 = today only",
        "zh": "从 intervals.icu 上传到 iGPSPORT / Bryton 的计划训练天数；1 = 仅今天",
    },
    "settings.activity_type": {
        "en": "Activity type on intervals.icu",
        "zh": "intervals.icu 活动类型",
    },
    "settings.activity_type.none": {
        "en": "Don't change (leave as uploaded)",
        "zh": "不修改（保持上传时的类型）",
    },
    # intervals.icu SportInfo api values → UI labels (key stays English for API)
    "settings.activity_type.Ride": {"en": "Ride", "zh": "骑行"},
    "settings.activity_type.MountainBikeRide": {
        "en": "Mountain Bike Ride",
        "zh": "山地骑行",
    },
    "settings.activity_type.GravelRide": {"en": "Gravel Ride", "zh": "砾石骑行"},
    "settings.activity_type.VirtualRide": {"en": "Virtual Ride", "zh": "虚拟骑行"},
    "settings.activity_type.EBikeRide": {"en": "E-Bike Ride", "zh": "电动助力骑行"},
    "settings.activity_type.EMountainBikeRide": {
        "en": "E-Mountain Bike Ride",
        "zh": "电动山地骑行",
    },
    "settings.activity_type.TrackRide": {"en": "Track Ride", "zh": "场地骑行"},
    "settings.activity_type.Cyclocross": {"en": "Cyclocross", "zh": "自行车越野"},
    "settings.activity_type.Handcycle": {"en": "Handcycle", "zh": "手摇自行车"},
    "settings.activity_type.Velomobile": {"en": "Velomobile", "zh": "躺式厢式自行车"},
    "settings.delete_after_upload": {
        "en": "Delete downloaded files after upload",
        "zh": "上传后删除本地下载文件",
    },
    "settings.force_resync": {
        "en": "Force re-sync (re-download even if already uploaded)",
        "zh": "强制重新同步（已上传也重新下载）",
    },
    "settings.auto_sync.enabled": {"en": "Auto-sync in background", "zh": "后台自动同步"},
    "settings.auto_sync.interval": {"en": "Auto-sync interval", "zh": "自动同步间隔"},
    "settings.auto_sync.interval.value": {
        "en": "Every {minutes} minutes",
        "zh": "每 {minutes} 分钟",
    },
    "settings.auto_sync.interval.tooltip": {"en": "Choose interval", "zh": "选择间隔"},
    "settings.auto_sync.helper.android": {
        "en": "Shorter intervals use more battery. On Android a persistent notification keeps sync running while enabled; force-stopping the app still stops auto-sync. On desktop, sync only runs while the app is open.",
        "zh": "间隔越短越耗电。Android 上启用时会有常驻通知以保持同步；强制停止应用仍会中断自动同步。桌面端仅在应用打开时运行。",
    },
    "settings.auto_sync.helper.desktop": {
        "en": "Shorter intervals use more battery. Auto-sync runs only while the app is open (use the CLI + Task Scheduler for unattended PC sync).",
        "zh": "间隔越短越耗电。自动同步仅在应用打开时运行（无人值守可用 CLI + 计划任务）。",
    },
    "settings.dropbox.title": {"en": "Dropbox", "zh": "Dropbox"},
    "settings.dropbox.subtitle": {"en": "Optional cloud backup", "zh": "可选云备份"},
    "settings.dropbox.connected": {"en": "Connected", "zh": "已连接"},
    "settings.dropbox.not_connected": {"en": "Not connected", "zh": "未连接"},
    "settings.dropbox.no_app_key": {
        "en": "Dropbox app key missing from this build",
        "zh": "此构建缺少 Dropbox app key",
    },
    "settings.dropbox.upload": {"en": "Upload activities to Dropbox", "zh": "上传活动到 Dropbox"},
    "settings.dropbox.folder": {"en": "Dropbox folder", "zh": "Dropbox 文件夹"},
    "settings.dropbox.folder.helper": {
        "en": "Dropbox path, e.g. /Fit files",
        "zh": "Dropbox 路径，例如 /Fit files",
    },
    "settings.dropbox.date_filenames": {
        "en": "Use date in Dropbox filenames",
        "zh": "Dropbox 文件名使用日期",
    },
    "settings.dropbox.filename_hint": {
        "en": "iGPSPORT: ride-0-YYYY-MM-DD-HH-MM-SS.fit · Bryton: YYMMDDHHMMSS.fit",
        "zh": "iGPSPORT: ride-0-YYYY-MM-DD-HH-MM-SS.fit · Bryton: YYMMDDHHMMSS.fit",
    },
    "settings.dropbox.auth_code": {
        "en": "Dropbox authorization code",
        "zh": "Dropbox 授权码",
    },
    "settings.dropbox.connect": {"en": "Connect Dropbox", "zh": "连接 Dropbox"},
    "settings.dropbox.finish": {"en": "Finish connection", "zh": "完成连接"},
    "settings.dropbox.disconnect": {"en": "Disconnect", "zh": "断开连接"},
    "settings.dropbox.snack.no_app_key": {
        "en": "Dropbox app key is missing from this build.",
        "zh": "此构建缺少 Dropbox app key。",
    },
    "settings.dropbox.snack.paste_code": {
        "en": "Paste the Dropbox authorization code here.",
        "zh": "请在此粘贴 Dropbox 授权码。",
    },
    "settings.dropbox.snack.start_first": {
        "en": "Start Dropbox connection first.",
        "zh": "请先开始 Dropbox 连接。",
    },
    "settings.dropbox.snack.paste_first": {
        "en": "Paste the Dropbox code first.",
        "zh": "请先粘贴 Dropbox 授权码。",
    },
    "settings.dropbox.snack.failed": {
        "en": "Dropbox connection failed: {exc}",
        "zh": "Dropbox 连接失败：{exc}",
    },
    "settings.dropbox.snack.no_token": {
        "en": "Dropbox did not return a refresh token.",
        "zh": "Dropbox 未返回 refresh token。",
    },
    "settings.dropbox.snack.connected": {"en": "Dropbox connected.", "zh": "Dropbox 已连接。"},
    "settings.dropbox.snack.disconnected": {
        "en": "Dropbox disconnected.",
        "zh": "Dropbox 已断开。",
    },
    "settings.profile.title": {"en": "iGPSPORT profile", "zh": "iGPSPORT 资料"},
    "settings.profile.subtitle": {
        "en": "FTP, LTHR, max HR, weight, and zones from intervals.icu",
        "zh": "从 intervals.icu 同步 FTP、LTHR、最大心率、体重与区间",
    },
    "settings.profile.checking": {"en": "Checking…", "zh": "检查中…"},
    "settings.profile.hint.no_creds": {
        "en": "Add iGPSPORT credentials and intervals.icu API key first.",
        "zh": "请先填写 iGPSPORT 凭据与 intervals.icu API 密钥。",
    },
    "settings.profile.sync_now": {"en": "Sync profile now", "zh": "立即同步资料"},
    "settings.profile.check_on_launch": {"en": "Check on app launch", "zh": "启动时检查"},
    "settings.storage.title": {"en": "Storage", "zh": "存储"},
    "settings.storage.subtitle": {
        "en": "Save to Downloads or app storage",
        "zh": "保存到下载目录或应用私有存储",
    },
    "settings.storage.save_to_downloads": {
        "en": "Save to phone's Downloads folder",
        "zh": "保存到手机「下载」文件夹",
    },
    "settings.storage.note.downloads_on": {
        "en": "Saved to your phone's Downloads folder (Download/intervalssync-fit).",
        "zh": "将保存到手机下载目录（Download/intervalssync-fit）。",
    },
    "settings.storage.note.downloads_off": {
        "en": 'Kept in the app\'s private storage and uploaded to intervals.icu (removed afterwards unless you turn that off). Turn on "Save to phone\'s Downloads folder" to keep them where you can find them.',
        "zh": "保存在应用私有存储并上传到 intervals.icu（除非关闭删除选项，否则上传后会删除）。打开「保存到手机下载文件夹」可便于查找。",
    },
    "settings.storage.download_folder": {"en": "Download folder", "zh": "下载文件夹"},
    "settings.storage.open_folder": {"en": "Open folder", "zh": "打开文件夹"},
    "settings.save.error.no_source": {
        "en": "Enable at least one activity source.",
        "zh": "请至少启用一个活动数据源。",
    },
    "settings.save.error.igp_user": {
        "en": "iGPSPORT account (email or phone) is required when enabled.",
        "zh": "启用 iGPSPORT 时必须填写账号（邮箱或手机号）。",
    },
    "settings.save.error.igp_password": {
        "en": "iGPSPORT password is required when enabled.",
        "zh": "启用 iGPSPORT 时必须填写密码。",
    },
    "settings.save.error.bryton_email": {
        "en": "Bryton Active email is required when enabled.",
        "zh": "启用 Bryton Active 时必须填写邮箱。",
    },
    "settings.save.error.bryton_password": {
        "en": "Bryton Active password is required when enabled.",
        "zh": "启用 Bryton Active 时必须填写密码。",
    },
    "settings.save.success.default": {
        "en": "Saved securely to your system credential store.",
        "zh": "已安全保存到系统凭据库。",
    },
    "settings.save.success.no_notify_perm": {
        "en": "Saved, but auto-sync stayed off — notification permission is required on Android.",
        "zh": "已保存，但自动同步未开启——Android 需要通知权限。",
    },
    "settings.save.success.battery_hint": {
        "en": "Saved with auto-sync on. For best results, allow unrestricted battery use for Intervals Sync in system settings.",
        "zh": "已保存并开启自动同步。建议在系统设置中允许 Intervals Sync 不受电池限制。",
    },
    "settings.save.success.dropbox_no_key": {
        "en": "Saved, but Dropbox is disabled because this build has no app key.",
        "zh": "已保存，但因缺少 app key，Dropbox 已禁用。",
    },
    "settings.save.success.dropbox_not_connected": {
        "en": "Saved, but Dropbox is disabled until you connect it.",
        "zh": "已保存，但需先连接 Dropbox 才能启用。",
    },
    "settings.save.success.storage_denied": {
        "en": "Saved, but storage permission wasn't granted — files stay in the app's private storage.",
        "zh": "已保存，但未授予存储权限——文件仍留在应用私有存储。",
    },

    # --- Sync view ---
    "sync.page.title": {"en": "Your rides, synced", "zh": "骑行记录，自动同步"},
    "sync.page.subtitle": {
        "en": "Pull recent activities from iGPSPORT or Bryton into intervals.icu, or push planned workouts the other way.",
        "zh": "将 iGPSPORT 或 Bryton 的近期活动同步到 intervals.icu，或把训练计划推送到设备端。",
    },
    "sync.source.igpsport": {"en": "iGPSPORT", "zh": "iGPSPORT"},
    "sync.source.bryton": {"en": "Bryton", "zh": "Bryton"},
    "sync.action.sync_activities": {"en": "Sync activities", "zh": "同步活动"},
    "sync.action.upload_workouts": {"en": "Upload workouts", "zh": "上传训练计划"},
    "sync.empty.no_source": {
        "en": "Enable a source in Settings to sync.",
        "zh": "请先在设置中启用数据源。",
    },
    "sync.log.title": {"en": "Activity log", "zh": "活动日志"},
    "sync.log.live": {"en": "live", "zh": "实时"},
    "sync.snack.no_igp_creds": {
        "en": "Add your iGPSPORT credentials in Settings first.",
        "zh": "请先在设置中填写 iGPSPORT 凭据。",
    },
    "sync.snack.no_bryton_creds": {
        "en": "Add your Bryton credentials in Settings first.",
        "zh": "请先在设置中填写 Bryton 凭据。",
    },
    "sync.snack.no_api_key": {
        "en": "Add your intervals.icu API key in Settings first.",
        "zh": "请先在设置中填写 intervals.icu API 密钥。",
    },
    "sync.snack.sync_busy": {
        "en": "A sync is already running. Try again in a moment.",
        "zh": "同步正在进行中，请稍后再试。",
    },
    "sync.log.done.activity": {
        "en": "Done — intervals uploaded {uploaded}, Dropbox uploaded {uploaded_dropbox}, downloaded {downloaded}, skipped {skipped}, Dropbox skipped {skipped_dropbox}, failed {failed}, Dropbox failed {failed_dropbox}.",
        "zh": "完成 — intervals 上传 {uploaded}，Dropbox 上传 {uploaded_dropbox}，下载 {downloaded}，跳过 {skipped}，Dropbox 跳过 {skipped_dropbox}，失败 {failed}，Dropbox 失败 {failed_dropbox}。",
    },
    "sync.log.done.workout": {
        "en": "Done — uploaded {uploaded}, skipped {skipped}, no steps {no_steps}, failed {failed}.",
        "zh": "完成 — 已上传 {uploaded}，跳过 {skipped}，无步骤 {no_steps}，失败 {failed}。",
    },
    "sync.log.error.unexpected": {
        "en": "✗ Unexpected error: {exc}",
        "zh": "✗ 意外错误：{exc}",
    },

    # --- Profile sync UI ---
    "profile.snack.no_creds": {
        "en": "Add iGPSPORT credentials and intervals.icu API key in Settings first.",
        "zh": "请先在设置中填写 iGPSPORT 凭据与 intervals.icu API 密钥。",
    },
    "profile.snack.updating": {"en": "Updating iGPSPORT profile…", "zh": "正在更新 iGPSPORT 资料…"},
    "profile.success.base": {"en": "iGPSPORT profile updated.", "zh": "iGPSPORT 资料已更新。"},
    "profile.success.with_values": {
        "en": "iGPSPORT profile updated — {parts}.",
        "zh": "iGPSPORT 资料已更新 — {parts}。",
    },
    "profile.success.part.ftp": {"en": "FTP {value}", "zh": "FTP {value}"},
    "profile.success.part.lthr": {"en": "LTHR {value}", "zh": "LTHR {value}"},
    "profile.success.part.mhr": {"en": "max HR {value}", "zh": "最大心率 {value}"},
    "profile.success.part.weight": {"en": "weight {value}", "zh": "体重 {value}"},
    "profile.error.unexpected": {"en": "Unexpected error: {exc}", "zh": "意外错误：{exc}"},
    "profile.dialog.title": {"en": "Update iGPSPORT profile?", "zh": "更新 iGPSPORT 资料？"},
    "profile.dialog.body": {
        "en": "Your iGPSPORT profile differs from intervals.icu:",
        "zh": "你的 iGPSPORT 资料与 intervals.icu 不一致：",
    },
    "profile.dialog.footer": {
        "en": "Power/HR zones and weight will be updated too.",
        "zh": "功率/心率区间与体重也会一并更新。",
    },
    "profile.dialog.not_now": {"en": "Not now", "zh": "暂时不要"},
    "profile.diff.label.ftp": {"en": "FTP", "zh": "FTP"},
    "profile.diff.label.lthr": {"en": "LTHR", "zh": "LTHR"},
    "profile.diff.label.mhr": {"en": "max HR", "zh": "最大心率"},
    "profile.diff.label.weight": {"en": "Weight", "zh": "体重"},
    "profile.diff.line": {
        "en": "{label}: iGPSPORT {current} → intervals.icu {desired}",
        # Keep ASCII ":" so format_threshold_status can split labels.
        "zh": "{label}: iGPSPORT {current} → intervals.icu {desired}",
    },
    "error.credentials.igpsport": {
        "en": "iGPSPORT credentials missing",
        "zh": "缺少 iGPSPORT 凭据",
    },
    "error.credentials.bryton": {
        "en": "Bryton credentials missing",
        "zh": "缺少 Bryton 凭据",
    },
    "error.api_key_required": {
        "en": "intervals.icu API key is required for upload.",
        "zh": "上传需要 intervals.icu API 密钥。",
    },
    "error.dropbox_app_key_required": {
        "en": "Dropbox app key is required for Dropbox upload.",
        "zh": "上传到 Dropbox 需要 Dropbox 应用密钥。",
    },
    "error.dropbox_connect_required": {
        "en": "Connect Dropbox in Settings before syncing.",
        "zh": "同步前请先在设置中连接 Dropbox。",
    },
    "sync.log.error.detail": {"en": "✗ {exc}", "zh": "✗ {exc}"},
    "profile.dialog.update_now": {"en": "Update now", "zh": "立即更新"},
    "profile.status.check_failed": {
        "en": "Could not check profile status.",
        "zh": "无法检查资料状态。",
    },
    "profile.status.in_sync": {
        "en": "In sync with intervals.icu.",
        "zh": "已与 intervals.icu 一致。",
    },
    "profile.status.out_of_sync.one": {"en": "Out of sync: {diff}", "zh": "不一致：{diff}"},
    "profile.status.out_of_sync.many": {"en": "Out of sync: {labels}", "zh": "不一致：{labels}"},

    # --- Auto-sync notifications ---
    "autosync.channel.name": {"en": "Auto-sync", "zh": "自动同步"},
    "autosync.channel.description": {
        "en": "Background activity sync for Intervals Sync",
        "zh": "Intervals Sync 后台活动同步",
    },
    "autosync.notification.title": {"en": "Intervals Sync", "zh": "Intervals Sync"},
    "autosync.notification.upload.one": {
        "en": "Uploaded {n} ride to intervals.icu",
        "zh": "已上传 {n} 条骑行到 intervals.icu",
    },
    "autosync.notification.upload.many": {
        "en": "Uploaded {n} rides to intervals.icu",
        "zh": "已上传 {n} 条骑行到 intervals.icu",
    },
    "autosync.fgs.title": {
        "en": "Intervals Sync — auto-sync on",
        "zh": "Intervals Sync — 自动同步已开启",
    },
    "autosync.fgs.body": {
        "en": "Checking for new rides every {interval} minutes",
        "zh": "每 {interval} 分钟检查新骑行",
    },

    # --- Gamification ranks ---
    "rank.rookie": {"en": "Rookie", "zh": "新手"},
    "rank.warmup": {"en": "Warm-up lap", "zh": "热身圈"},
    "rank.domestique": {"en": "Domestique", "zh": "爬坡手"},
    "rank.breakaway": {"en": "Breakaway", "zh": "突围"},
    "rank.climber": {"en": "Climber", "zh": "登山手"},
    "rank.sprinter": {"en": "Sprinter", "zh": "冲刺手"},
    "rank.century": {"en": "Century rider", "zh": "百骑骑士"},
    "rank.grand_tourer": {"en": "Grand tourer", "zh": "环赛车手"},

    # --- Milestones ---
    "milestone.title.5": {"en": "Domestique status!", "zh": "爬坡手达成！"},
    "milestone.title.25": {"en": "Quarter century!", "zh": "四分之一世纪！"},
    "milestone.title.50": {"en": "Half century!", "zh": "半程世纪！"},
    "milestone.title.100": {"en": "Century!", "zh": "世纪骑！"},
    "milestone.title.250": {"en": "Grand tour stage!", "zh": "环赛赛段！"},
    "milestone.title.500": {"en": "Monument ride!", "zh": "古典赛级别！"},
    "milestone.title.1000": {"en": "Legend status!", "zh": "传奇达成！"},
    "milestone.title.fallback": {"en": "{n} transfers!", "zh": "{n} 次传输！"},
    "milestone.msg.5": {
        "en": "Five activities synced on autopilot. Your training log just got a lot easier.",
        "zh": "已自动同步五条活动。训练日志轻松多了。",
    },
    "milestone.msg.25": {
        "en": "Twenty-five rides across, hands-free. You're in a proper rhythm now.",
        "zh": "二十五次骑行免动手同步，节奏已成。",
    },
    "milestone.msg.50": {
        "en": "Fifty transfers done — that's a serious stack of saved clicks.",
        "zh": "五十次传输完成——省下了大量点击。",
    },
    "milestone.msg.100": {
        "en": "One hundred activities on autopilot. Every ride, right where it belongs.",
        "zh": "一百条活动自动到位，每次骑行各归其位。",
    },
    "milestone.msg.250": {
        "en": "250 syncs deep. Your data flows like a freshly-oiled drivetrain.",
        "zh": "已同步 250 次，数据流畅如新上油的传动系统。",
    },
    "milestone.msg.500": {
        "en": "Five hundred transfers. That's real dedication — and a lot of saved time.",
        "zh": "五百次传输，既是坚持，也是大量节省的时间。",
    },
    "milestone.msg.1000": {
        "en": "One thousand syncs. You've officially reached legend status.",
        "zh": "一千次同步，正式进入传奇行列。",
    },
    "milestone.msg.fallback": {
        "en": "{n} activities synced on autopilot. Nice work keeping your training data flowing.",
        "zh": "已自动同步 {n} 条活动，训练数据持续流转，干得漂亮。",
    },

    # --- Stats / Ko-fi (en) / Partner (zh) ---
    "stats.eyebrow": {"en": "LIFETIME SYNCS", "zh": "累计同步"},
    "stats.breakdown": {
        "en": "{activities} {activity_word} · {workouts} {workout_word}",
        "zh": "{activities} 条活动 · {workouts} 个训练",
    },
    "stats.activity.one": {"en": "activity", "zh": "条活动"},
    "stats.activity.many": {"en": "activities", "zh": "条活动"},
    "stats.workout.one": {"en": "workout", "zh": "个训练"},
    "stats.workout.many": {"en": "workouts", "zh": "个训练"},
    "stats.target.next": {"en": "Next milestone · {n}", "zh": "下一里程碑 · {n}"},
    "stats.target.all_done": {"en": "Every milestone cleared", "zh": "全部里程碑已达成"},
    "stats.remaining": {"en": "{n} {word} to go", "zh": "还差 {n} {word}"},
    "stats.sync.one": {"en": "sync", "zh": "次同步"},
    "stats.sync.many": {"en": "syncs", "zh": "次同步"},
    "stats.remaining.legend": {"en": "Legend", "zh": "传奇"},
    "stats.kofi_button": {
        "en": "Saved you time? Buy me a coffee",
        "zh": "了解耐力单车",
    },
    "kofi.tooltip": {"en": "Support on Ko-fi", "zh": "了解耐力单车"},
    "kofi.dialog.title": {"en": "Support development", "zh": "耐力单车"},
    "kofi.dialog.body": {
        "en": "If Intervals Sync saves you time, consider supporting development on Ko-fi. Tips help fund bug fixes, releases, and new features.",
        "zh": "本简体中文版由耐力单车获得授权，并完成界面与文案本地化。基于开源项目 Intervals Sync。",
    },
    "kofi.dialog.not_now": {"en": "Not now", "zh": "暂时不要"},
    "kofi.dialog.support": {"en": "Support on Ko-fi", "zh": "知道了"},
    "partner.slogan": {
        "en": "",
        "zh": "极致性价比的自行车功率训练营",
    },
    "celebration.syncs_completed": {"en": "SYNCS COMPLETED", "zh": "同步完成"},
    "celebration.kofi_line": {
        "en": "Intervals Sync is free and built in spare time. A small Ko-fi keeps it rolling.",
        "zh": "简体中文版由耐力单车授权本地化。",
    },
    "celebration.buy_coffee": {"en": "Buy me a coffee", "zh": "了解耐力单车"},
    "celebration.keep_rolling": {"en": "Keep rolling", "zh": "继续前进"},

    # --- Sync runner ---
    "progress.autosync.igpsport": {"en": "Auto-sync: iGPSPORT…", "zh": "自动同步：iGPSPORT…"},
    "progress.autosync.bryton": {"en": "Auto-sync: Bryton…", "zh": "自动同步：Bryton…"},
    "progress.error.igpsport": {"en": "✗ iGPSPORT: {exc}", "zh": "✗ iGPSPORT：{exc}"},
    "progress.error.igpsport.unexpected": {
        "en": "✗ iGPSPORT unexpected error: {exc}",
        "zh": "✗ iGPSPORT 意外错误：{exc}",
    },
    "progress.error.bryton": {"en": "✗ Bryton: {exc}", "zh": "✗ Bryton：{exc}"},
    "progress.error.bryton.unexpected": {
        "en": "✗ Bryton unexpected error: {exc}",
        "zh": "✗ Bryton 意外错误：{exc}",
    },

    # --- Shared progress ---
    "progress.login.igpsport": {"en": "Logging in to iGPSPORT…", "zh": "正在登录 iGPSPORT…"},
    "progress.login.bryton": {"en": "Logging in to Bryton Active…", "zh": "正在登录 Bryton Active…"},
    "progress.login.done": {"en": "Logged in.", "zh": "已登录。"},
    "progress.list.found": {"en": "Found {n} activities.", "zh": "找到 {n} 条活动。"},
    "progress.list.item": {
        "en": "  • {id} | {start_time} | {title}",
        "zh": "  • {id} | {start_time} | {title}",
    },
    "progress.intervals.already.range": {
        "en": "{n} activities already on intervals.icu in {oldest}…{newest}.",
        "zh": "intervals.icu 上已有 {n} 条活动（{oldest}…{newest}）。",
    },
    "progress.intervals.already.range_simple": {
        "en": "{n} activities already on intervals.icu in this date range.",
        "zh": "该日期范围内 intervals.icu 已有 {n} 条活动。",
    },
    "progress.intervals.check_failed": {
        "en": "⚠ Could not check intervals.icu (will process all): {exc}",
        "zh": "⚠ 无法检查 intervals.icu（将处理全部）：{exc}",
    },
    "progress.dropbox.already": {
        "en": "{n} activities already in Dropbox.",
        "zh": "Dropbox 中已有 {n} 条活动。",
    },
    "progress.dropbox.check_failed": {
        "en": "⚠ Could not check Dropbox (will process all): {exc}",
        "zh": "⚠ 无法检查 Dropbox（将处理全部）：{exc}",
    },
    "progress.skip.intervals": {
        "en": "↷ Skipping {id} — already on intervals.icu.",
        "zh": "↷ 跳过 {id} — 已在 intervals.icu。",
    },
    "progress.skip.dropbox": {
        "en": "↷ Skipping {id} — already in Dropbox.",
        "zh": "↷ 跳过 {id} — 已在 Dropbox。",
    },
    "progress.fit_url.missing": {
        "en": "⚠ Could not resolve FIT URL for {id}; skipping.",
        "zh": "⚠ 无法解析 {id} 的 FIT 链接，已跳过。",
    },
    "progress.fit_url.info": {"en": "FIT URL for {id}: {url}", "zh": "{id} 的 FIT 链接：{url}"},
    "progress.download": {"en": "Downloading {id}…", "zh": "正在下载 {id}…"},
    "progress.download.fail": {
        "en": "⚠ Could not download FIT for {id}: {exc}",
        "zh": "⚠ 无法下载 {id} 的 FIT：{exc}",
    },
    "progress.upload.intervals.ok": {
        "en": "✓ Uploaded {id}: {title}",
        "zh": "✓ 已上传 {id}：{title}",
    },
    "progress.upload.intervals.fail": {
        "en": "✗ Failed to upload {id}.",
        "zh": "✗ 上传 {id} 失败。",
    },
    "progress.activity_type.ok": {"en": "↻ Set {id} → {type}", "zh": "↻ 已设置 {id} → {type}"},
    "progress.activity_type.fail": {
        "en": "⚠ Could not set activity type for {id}.",
        "zh": "⚠ 无法为 {id} 设置活动类型。",
    },
    "progress.upload.dropbox.start": {
        "en": "Uploading {id} to Dropbox…",
        "zh": "正在上传 {id} 到 Dropbox…",
    },
    "progress.upload.dropbox.fail": {
        "en": "⚠ Dropbox upload failed for {id}: {exc}",
        "zh": "⚠ {id} 上传 Dropbox 失败：{exc}",
    },
    "progress.upload.dropbox.ok": {
        "en": "✓ Uploaded {id} to Dropbox",
        "zh": "✓ 已上传 {id} 到 Dropbox",
    },
    "progress.file.removed": {
        "en": "  Removed local file {filename}",
        "zh": "  已删除本地文件 {filename}",
    },
    "progress.workout.library.igpsport": {
        "en": "Found {n} custom workouts on iGPSPORT.",
        "zh": "在 iGPSPORT 找到 {n} 个自定义训练。",
    },
    "progress.workout.library.bryton": {
        "en": "Found {n} custom workouts on Bryton.",
        "zh": "在 Bryton 找到 {n} 个自定义训练。",
    },
    "progress.workout.fetch.start": {
        "en": "Fetching planned workouts from intervals.icu…",
        "zh": "正在从 intervals.icu 获取计划训练…",
    },
    "progress.workout.fetch.found": {
        "en": "Found {n} planned workouts.",
        "zh": "找到 {n} 个计划训练。",
    },
    "progress.workout.skip.unsupported": {
        "en": "↷ Skipping {name} — unsupported type {type} (cycling only in v1).",
        "zh": "↷ 跳过 {name} — 不支持的类型 {type}（v1 仅支持骑行）。",
    },
    "progress.workout.skip.igpsport": {
        "en": "↷ Skipping {name} — already on iGPSPORT.",
        "zh": "↷ 跳过 {name} — 已在 iGPSPORT。",
    },
    "progress.workout.skip.bryton": {
        "en": "↷ Skipping {name} — already on Bryton.",
        "zh": "↷ 跳过 {name} — 已在 Bryton。",
    },
    "progress.workout.skip.no_steps": {
        "en": "⚠ Skipping {name} — no structured steps (open the workout in intervals.icu first).",
        "zh": "⚠ 跳过 {name} — 无结构化步骤（请先在 intervals.icu 打开该训练）。",
    },
    "progress.workout.upload.start": {"en": "Uploading {name}…", "zh": "正在上传 {name}…"},
    "progress.workout.upload.ok.igpsport": {
        "en": "✓ Uploaded {name} (workoutId {id})",
        "zh": "✓ 已上传 {name}（workoutId {id}）",
    },
    "progress.workout.upload.ok.bryton": {
        "en": "✓ Uploaded {name} ({upload_name}.fit)",
        "zh": "✓ 已上传 {name}（{upload_name}.fit）",
    },
    "progress.workout.upload.fail": {
        "en": "✗ Failed to upload {name}.",
        "zh": "✗ 上传 {name} 失败。",
    },
    "progress.profile.fetch.settings": {
        "en": "Fetching sport settings from intervals.icu…",
        "zh": "正在从 intervals.icu 获取运动设置…",
    },
    "progress.profile.fetch.weight": {
        "en": "Fetching athlete weight from intervals.icu…",
        "zh": "正在从 intervals.icu 获取运动员体重…",
    },
    "progress.profile.fetch.profile": {
        "en": "Fetching iGPSPORT profile…",
        "zh": "正在获取 iGPSPORT 资料…",
    },
    "progress.profile.update": {"en": "Updating iGPSPORT profile…", "zh": "正在更新 iGPSPORT 资料…"},
    "progress.profile.update.weight": {
        "en": "Updating iGPSPORT weight…",
        "zh": "正在更新 iGPSPORT 体重…",
    },
    "progress.profile.location_cleared": {
        "en": "Note: iGPSPORT cleared profile location while updating weight; set location again in the app.",
        "zh": "注意：更新体重时 iGPSPORT 清除了资料位置；请在 App 中重新设置位置。",
    },
    "progress.profile.verify": {"en": "Verifying iGPSPORT profile…", "zh": "正在验证 iGPSPORT 资料…"},
    "progress.profile.summary.label": {"en": "{label}:", "zh": "{label}："},
    "progress.profile.summary.member": {"en": "  member: {parts}", "zh": "  成员：{parts}"},
    "progress.profile.summary.power": {"en": "  power:  {ranges}", "zh": "  功率：{ranges}"},
    "progress.profile.summary.heartrate": {
        "en": "  heartRate: {ranges}",
        "zh": "  心率：{ranges}",
    },
    "progress.profile.label.before": {"en": "Before", "zh": "更新前"},
    "progress.profile.label.after": {"en": "After", "zh": "更新后"},
    "progress.profile.label.readback": {"en": "Read-back", "zh": "回读"},
}
# fmt: on


def normalize_language(value: str | None) -> Language:
    if not value:
        return "en"
    lowered = value.strip().lower().replace("_", "-")
    if lowered == "zh" or lowered.startswith("zh-"):
        return "zh"
    if lowered in _VALID:
        return lowered  # type: ignore[return-value]
    return "en"


def _android_prop_language() -> str | None:
    """Read locale from Android system props when embedded Python has no LANG."""
    for path in ("/system/build.prop", "/system/etc/prop.default"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            if line.startswith(("persist.sys.locale=", "ro.product.locale=")):
                return line.split("=", 1)[1].strip() or None
    return None


def detect_system_language() -> Language:
    """Detect OS UI language. Chinese Windows / Android / macOS → zh."""
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (lang_id & 0xFF) == _WIN_LANG_CHINESE:
                return "zh"
        except Exception:  # noqa: BLE001
            pass

    lang: str | None = None
    try:
        lang, _ = locale.getlocale()
    except Exception:  # noqa: BLE001
        lang = None
    if not lang:
        for env_key in ("LANG", "LC_ALL", "LC_MESSAGES"):
            value = os.environ.get(env_key)
            if value:
                lang = value.split(".")[0]
                break
    if not lang:
        lang = _android_prop_language()
    return normalize_language(lang)


def activity_type_label(api_value: str) -> str:
    """Localized label for an intervals.icu cycling sport API value."""
    if not api_value:
        return t("settings.activity_type.none")
    key = f"settings.activity_type.{api_value}"
    label = t(key)
    return api_value if label == key else label


_EXACT_ERROR_KEYS: dict[str, str] = {
    "intervals.icu API key is required for upload.": "error.api_key_required",
    "Dropbox app key is required for Dropbox upload.": "error.dropbox_app_key_required",
    "Connect Dropbox in Settings before syncing.": "error.dropbox_connect_required",
    "iGPSPORT credentials missing": "error.credentials.igpsport",
    "Bryton credentials missing": "error.credentials.bryton",
}


def localize_user_error(exc: BaseException | str) -> str:
    """Map known English sync/auth errors to the active UI language."""
    message = str(exc)
    key = _EXACT_ERROR_KEYS.get(message)
    return t(key) if key else message


def get_language() -> Language:
    return _current


def set_language(language: str | None) -> Language:
    global _current
    _current = normalize_language(language)
    return _current


def is_chinese() -> bool:
    return _current == "zh"


def t(key: str, **kwargs: object) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        text = key
    else:
        text = entry.get(_current) or entry.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
