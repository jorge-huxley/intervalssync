"""Single source of the app version at runtime.

Local/dev keeps the placeholder below. CI overwrites this file with the git tag
just before building (see .github/workflows/release.yml), so released builds
report their real version (used by the in-app About dialog).
"""

__version__ = "0.0.0+dev"
