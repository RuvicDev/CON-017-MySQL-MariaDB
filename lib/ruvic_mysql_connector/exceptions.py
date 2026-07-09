"""Excepciones propias del conector MySQL / MariaDB.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del driver subyacente.
"""


class MysqlConnectorError(Exception):
    """Error base del conector."""


class MysqlAuthError(MysqlConnectorError):
    """Credenciales inválidas o permisos insuficientes."""


class MysqlNetworkError(MysqlConnectorError):
    """No se pudo alcanzar el servidor (host/puerto/red/timeout)."""


class MysqlDataError(MysqlConnectorError):
    """La operación es válida pero el objeto no existe o el query es inválido."""
