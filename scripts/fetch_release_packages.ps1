# Download official v0.9.1 Windows / macOS / Android packages into dist/.
# Uses BitsTransfer (background, resumable) — better than curl on slow links.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$base = "https://github.com/jorge-huxley/intervalssync/releases/download/v0.9.1"
$files = @(
    "intervalssync-v0.9.1-windows.zip",
    "intervalssync-v0.9.1-macos.zip",
    "intervalssync-v0.9.1-android.apk"
)
foreach ($name in $files) {
    $url = "$base/$name"
    $out = Join-Path $dist $name
    Write-Host "Downloading $name ..."
    Start-BitsTransfer -Source $url -Destination $out -DisplayName $name
    $len = (Get-Item $out).Length
    if ($len -lt 1MB) { throw "Download too small: $name ($len bytes)" }
    Write-Host "OK $name ($len bytes)"
}
Get-ChildItem $dist | Format-Table Name, Length -AutoSize
