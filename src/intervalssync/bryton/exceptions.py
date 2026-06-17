"""Bryton-specific errors."""


class BrytonSyncError(Exception):
    """Base class for Bryton sync errors shown to users."""


class BrytonAuthError(BrytonSyncError):
    """Login failed."""


class BrytonDDPError(BrytonSyncError):
    """DDP transport or protocol failure."""
