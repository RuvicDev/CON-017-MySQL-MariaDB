"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_MYSQL_.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PREFIX = "RUVIC_MYSQL_"


@dataclass(frozen=True)
class MysqlConfig:
    """Parámetros de conexión a MySQL / MariaDB."""

    host: str
    port: int
    database: str
    username: str
    password: str
    connect_timeout: int = 10

    @classmethod
    def from_env(cls) -> "MysqlConfig":
        """Construye la configuración desde las variables RUVIC_MYSQL_*.

        Raises:
            ValueError: si falta alguna variable obligatoria.

        Ejemplo:
            >>> config = MysqlConfig.from_env()
            >>> config.host
            'db.empresa.com'
        """
        missing = [
            f"{ENV_PREFIX}{name}"
            for name in ("HOST", "DATABASE", "USERNAME", "PASSWORD")
            if not os.environ.get(f"{ENV_PREFIX}{name}")
        ]
        if missing:
            raise ValueError(
                "Faltan variables de entorno del conector mysql: "
                + ", ".join(missing)
                + ". Configura el conector en Settings → Conectores."
            )
        return cls(
            host=os.environ[f"{ENV_PREFIX}HOST"],
            port=int(os.environ.get(f"{ENV_PREFIX}PORT", "3306")),
            database=os.environ[f"{ENV_PREFIX}DATABASE"],
            username=os.environ[f"{ENV_PREFIX}USERNAME"],
            password=os.environ[f"{ENV_PREFIX}PASSWORD"],
            connect_timeout=int(os.environ.get(f"{ENV_PREFIX}CONNECT_TIMEOUT", "10")),
        )
