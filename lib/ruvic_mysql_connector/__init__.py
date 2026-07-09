"""Conector Ruvic de solo lectura para MySQL / MariaDB."""

from .client import MysqlClient
from .config import ENV_PREFIX, MysqlConfig
from .exceptions import (
    MysqlAuthError,
    MysqlConnectorError,
    MysqlDataError,
    MysqlNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "MysqlAuthError",
    "MysqlClient",
    "MysqlConfig",
    "MysqlConnectorError",
    "MysqlDataError",
    "MysqlNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"
