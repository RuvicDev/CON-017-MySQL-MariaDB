"""Cliente de solo lectura para MySQL / MariaDB.

Capacidades:
- list_tables():      listar tablas de la base de datos.
- read_table():       leer filas de una tabla con límite.
- table_stats():      estadísticas de una tabla (filas, tamaño, columnas).
- explain_query():    plan de ejecución de un query SIN ejecutarlo.

Las credenciales SIEMPRE provienen de variables de entorno RUVIC_MYSQL_*
(ver config.MysqlConfig.from_env). Prohibido hardcodearlas.
"""

from __future__ import annotations

import json
import re
from typing import Any

import mysql.connector
from mysql.connector import Error as MysqlDriverError
from mysql.connector import errorcode

from .config import MysqlConfig
from .exceptions import (
    MysqlAuthError,
    MysqlConnectorError,
    MysqlDataError,
    MysqlNetworkError,
)
from .logging_utils import get_logger

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _has_multiple_statements(sql: str) -> bool:
    """Detecta un ';' que separa sentencias reales, ignorando los que
    aparecen dentro de literales de texto (ej. WHERE nota = 'a; b')."""
    return ";" in _STRING_LITERAL_RE.sub("", sql)

_AUTH_ERRNOS = {
    errorcode.ER_ACCESS_DENIED_ERROR,
    errorcode.ER_DBACCESS_DENIED_ERROR,
}
_PERMISSION_ERRNOS = {
    errorcode.ER_TABLEACCESS_DENIED_ERROR,
    errorcode.ER_COLUMNACCESS_DENIED_ERROR,
    errorcode.ER_DBACCESS_DENIED_ERROR,
}
_MISSING_OBJECT_ERRNOS = {
    errorcode.ER_BAD_DB_ERROR,
    errorcode.ER_NO_SUCH_TABLE,
}


def _wrap_query_error(exc: MysqlDriverError, not_found_message: str) -> MysqlConnectorError:
    """Traduce un error del driver ocurrido durante una consulta a una
    excepción propia, sin dejar escapar nunca el tipo crudo del driver."""
    errno = getattr(exc, "errno", None)
    if errno in _PERMISSION_ERRNOS:
        return MysqlAuthError(
            "El usuario no tiene permiso SELECT sobre ese esquema o tabla. "
            "Revisa el GRANT en el servidor."
        )
    if errno in _MISSING_OBJECT_ERRNOS:
        return MysqlDataError(not_found_message)
    return MysqlDataError(f"Error de datos: {exc}")


def _human_size(num_bytes: int | None) -> str:
    """Convierte bytes a un tamaño legible (ej. "12 MB")."""
    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _validate_identifier(name: str, kind: str) -> None:
    """Valida nombres de tabla/esquema para evitar inyección SQL."""
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise MysqlDataError(
            f"Nombre de {kind} inválido: {name!r}. "
            "Solo se permiten letras, números y guion bajo."
        )


def _validate_limit(limit: Any, max_limit: int) -> int:
    """Convierte y acota `limit`, sin dejar escapar TypeError/ValueError crudos."""
    try:
        return max(1, min(int(limit), max_limit))
    except (TypeError, ValueError) as exc:
        raise MysqlDataError(
            f"limit inválido: {limit!r}. Debe ser un número entero."
        ) from exc


class MysqlClient:
    """Cliente de solo lectura para MySQL / MariaDB.

    Args:
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_MYSQL_* (comportamiento estándar
            en el runtime de la plataforma).

    Ejemplo:
        >>> client = MysqlClient()          # lee RUVIC_MYSQL_* del entorno
        >>> client.list_tables()
        [{'schema': 'demo', 'table': 'clientes', 'rows_estimate': 1520}]
    """

    def __init__(self, config: MysqlConfig | None = None) -> None:
        self.config = config or MysqlConfig.from_env()
        self._logger = get_logger()

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _connect(self):
        try:
            conn = mysql.connector.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                connection_timeout=self.config.connect_timeout,
            )
        except MysqlDriverError as exc:
            errno = getattr(exc, "errno", None)
            if errno in _AUTH_ERRNOS:
                raise MysqlAuthError(
                    "Autenticación fallida: usuario o contraseña inválidos, "
                    "o el usuario no tiene acceso a la base de datos."
                ) from exc
            if errno == errorcode.ER_BAD_DB_ERROR:
                raise MysqlDataError(
                    f"La base de datos {self.config.database!r} no existe."
                ) from exc
            raise MysqlNetworkError(
                f"No se pudo conectar a {self.config.host}:{self.config.port} "
                f"(timeout {self.config.connect_timeout}s). Verifica host, puerto "
                "y acceso de red."
            ) from exc

        try:
            cur = conn.cursor()
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.close()
        except MysqlDriverError:
            # Algunas versiones muy antiguas de MariaDB no soportan esta
            # sentencia; el conector solo emite SELECT/EXPLAIN de todas
            # formas, así que no es fatal.
            self._logger.warning(
                "No se pudo forzar sesión de solo lectura; continuando de todos modos"
            )
        return conn

    def ping(self) -> bool:
        """Verifica la conexión ejecutando SELECT 1.

        Returns:
            True si la conexión funciona.

        Raises:
            MysqlAuthError / MysqlNetworkError / MysqlDataError según el fallo.
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        finally:
            conn.close()
        self._logger.info("Ping exitoso a %s:%s", self.config.host, self.config.port)
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1: listar tablas
    # ------------------------------------------------------------------ #

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        """Lista las tablas de un esquema con su conteo estimado de filas.

        Args:
            schema: esquema a inspeccionar (default: la base de datos
                configurada en RUVIC_MYSQL_DATABASE).

        Returns:
            Lista de dicts: {"schema", "table", "rows_estimate"}.

        Ejemplo:
            >>> client.list_tables()
            [{'schema': 'demo', 'table': 'ventas', 'rows_estimate': 89123}]
        """
        schema = schema or self.config.database
        _validate_identifier(schema, "esquema")
        query = """
            SELECT TABLE_SCHEMA AS schema_name,
                   TABLE_NAME   AS table_name,
                   TABLE_ROWS   AS rows_estimate
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(query, (schema,))
            rows = [
                {"schema": row[0], "table": row[1], "rows_estimate": row[2]}
                for row in cur.fetchall()
            ]
            cur.close()
        finally:
            conn.close()
        self._logger.info("Se listaron %d tablas del esquema %s", len(rows), schema)
        return rows

    # ------------------------------------------------------------------ #
    # Capacidad 2: leer una tabla
    # ------------------------------------------------------------------ #

    def read_table(
        self,
        table: str,
        schema: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lee filas de una tabla como lista de diccionarios.

        Args:
            table: nombre de la tabla.
            schema: esquema (default: la base de datos configurada).
            limit: máximo de filas a retornar (default 100, máximo 10000).

        Returns:
            Lista de dicts, una entrada por fila.

        Ejemplo:
            >>> client.read_table("clientes", limit=5)
            [{'id': 1, 'nombre': 'ACME', ...}, ...]
        """
        schema = schema or self.config.database
        _validate_identifier(table, "tabla")
        _validate_identifier(schema, "esquema")
        limit = _validate_limit(limit, 10_000)
        query = f"SELECT * FROM `{schema}`.`{table}` LIMIT %s"
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=True)
            try:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
            except MysqlDriverError as exc:
                raise _wrap_query_error(
                    exc, f'La tabla "{schema}"."{table}" no existe.'
                ) from exc
            cur.close()
        finally:
            conn.close()
        self._logger.info(
            'Leídas %d filas de "%s"."%s" (limit=%d)', len(rows), schema, table, limit
        )
        return rows

    # ------------------------------------------------------------------ #
    # Capacidad 3: estadísticas de una tabla
    # ------------------------------------------------------------------ #

    def table_stats(self, table: str, schema: str | None = None) -> dict[str, Any]:
        """Obtiene estadísticas de una tabla.

        Args:
            table: nombre de la tabla.
            schema: esquema (default: la base de datos configurada).

        Returns:
            Dict con: row_count (exacto), total_size (legible, ej. "12 MB"),
            y columns (lista de {"name", "type", "nullable"}).

        Ejemplo:
            >>> client.table_stats("ventas")
            {'row_count': 89123, 'total_size': '12.0 MB', 'columns': [...]}
        """
        schema = schema or self.config.database
        _validate_identifier(table, "tabla")
        _validate_identifier(schema, "esquema")
        qualified = f"`{schema}`.`{table}`"
        columns_query = """
            SELECT COLUMN_NAME AS name,
                   DATA_TYPE   AS type,
                   IS_NULLABLE = 'YES' AS nullable
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """
        size_query = """
            SELECT DATA_LENGTH, INDEX_LENGTH
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """
        not_found = f"La tabla {qualified} no existe."
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute(columns_query, (schema, table))
                columns = [
                    {"name": row[0], "type": row[1], "nullable": bool(row[2])}
                    for row in cur.fetchall()
                ]
                if not columns:
                    raise MysqlDataError(not_found)

                cur.execute(size_query, (schema, table))
                size_row = cur.fetchone()
                data_length, index_length = (size_row or (0, 0))

                cur.execute(f"SELECT COUNT(*) FROM {qualified}")
                row_count = cur.fetchone()[0]
            except MysqlDriverError as exc:
                raise _wrap_query_error(exc, not_found) from exc
            cur.close()
        finally:
            conn.close()
        return {
            "schema": schema,
            "table": table,
            "row_count": row_count,
            "total_size": _human_size((data_length or 0) + (index_length or 0)),
            "columns": columns,
        }

    # ------------------------------------------------------------------ #
    # Capacidad 4: EXPLAIN de un query (NUNCA lo ejecuta)
    # ------------------------------------------------------------------ #

    def explain_query(self, query: str) -> dict[str, Any]:
        """Describe el plan de ejecución de un query SIN ejecutarlo.

        Usa EXPLAIN FORMAT=JSON — el optimizador solo planifica el query,
        nunca se ejecuta ni modifica datos.

        Args:
            query: consulta SQL a analizar (solo se permite un statement,
                y debe ser un SELECT).

        Returns:
            Dict con: query_cost estimado (si el motor lo reporta) y el
            plan completo como árbol JSON.

        Ejemplo:
            >>> client.explain_query("SELECT * FROM ventas WHERE anio = 2026")
            {'query_cost': 1543.2, 'plan': {...}}
        """
        statement = query.strip().rstrip(";")
        if _has_multiple_statements(statement):
            raise MysqlDataError(
                "Solo se permite analizar un statement a la vez (sin ';')."
            )
        if not statement.lower().lstrip().startswith("select"):
            raise MysqlDataError(
                "explain_query solo acepta sentencias SELECT."
            )
        conn = self._connect()
        try:
            cur = conn.cursor()
            try:
                cur.execute(f"EXPLAIN FORMAT=JSON {statement}")
                (raw_plan,) = cur.fetchone()
            except MysqlDriverError as exc:
                raise _wrap_query_error(
                    exc, f"Query inválido, no se pudo planificar: {exc}"
                ) from exc
            cur.close()
        finally:
            conn.close()

        plan = json.loads(raw_plan)
        query_block = plan.get("query_block", {})
        # MySQL anida el costo en query_block.cost_info.query_cost; MariaDB
        # lo reporta directo en query_block.cost. Se intenta el formato de
        # MySQL primero y se cae al de MariaDB si no está presente.
        query_cost = query_block.get("cost_info", {}).get("query_cost")
        if query_cost is None:
            query_cost = query_block.get("cost")
        return {
            "query_cost": float(query_cost) if query_cost is not None else None,
            "plan": plan,
        }
