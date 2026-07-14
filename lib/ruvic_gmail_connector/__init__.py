"""Conector Ruvic para Gmail (Google Workspace)."""

from .client import GmailClient
from .config import ENV_PREFIX, GmailConfig
from .exceptions import (
    GmailAuthError,
    GmailConnectorError,
    GmailDataError,
    GmailNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "GmailAuthError",
    "GmailClient",
    "GmailConfig",
    "GmailConnectorError",
    "GmailDataError",
    "GmailNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"
