"""Prueba de conexión estándar del conector mysql.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_MYSQL_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Conecta a MySQL/MariaDB y ejecuta SELECT 1 usando las env vars RUVIC_MYSQL_*."""
    try:
        from ruvic_mysql_connector import (
            MysqlAuthError,
            MysqlClient,
            MysqlDataError,
            MysqlNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-mysql-connector no está instalada. "
            "Instala con: pip install git+https://github.com/Dgirto/"
            "MySQL-MariaDB.git#subdirectory=lib",
        )

    try:
        client = MysqlClient()  # valida que existan las env vars
    except ValueError as exc:
        return False, str(exc)

    try:
        client.ping()
    except MysqlAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except MysqlNetworkError as exc:
        return False, f"Error de red: {exc}"
    except MysqlDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa a {client.config.host}:{client.config.port}/"
        f"{client.config.database}",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)
