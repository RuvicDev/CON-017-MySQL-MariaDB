---
name: mysql
description: >
  Usa la librería ruvic_mysql_connector para consultar bases de datos MySQL
  o MariaDB en modo solo lectura - listar tablas (list_tables), leer datos
  (read_table), obtener estadísticas de tablas (table_stats) y analizar el
  plan de ejecución de un query sin ejecutarlo (explain_query). Úsala cuando
  el usuario pida consultar, explorar o analizar una base de datos MySQL o
  MariaDB.
triggers:
- mysql
- mariadb
- base de datos
- consultar tabla
- explain
---

# Conector MySQL / MariaDB (ruvic_mysql_connector)

Librería Python de solo lectura para MySQL y MariaDB. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/conector-mysql.git#subdirectory=lib`).

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `mysql` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_MYSQL_HOST` | Host del servidor |
| `RUVIC_MYSQL_PORT` | Puerto (default 3306) |
| `RUVIC_MYSQL_DATABASE` | Nombre de la base de datos |
| `RUVIC_MYSQL_USERNAME` | Usuario |
| `RUVIC_MYSQL_PASSWORD` | Contraseña |
| `RUVIC_MYSQL_CONNECT_TIMEOUT` | (opcional) timeout en segundos |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**.

## Conexión (siempre igual)

```python
from ruvic_mysql_connector import MysqlClient

client = MysqlClient()  # lee RUVIC_MYSQL_* del entorno automáticamente
```

## Capacidad 1 — Listar tablas

```python
tables = client.list_tables()
for t in tables:
    print(f"{t['schema']}.{t['table']}: ~{t['rows_estimate']} filas")
```

## Capacidad 2 — Leer una tabla

```python
rows = client.read_table("clientes", limit=50)
for row in rows:
    print(row)  # cada fila es un dict {columna: valor}
```

## Capacidad 3 — Estadísticas de una tabla

```python
stats = client.table_stats("ventas")
print(f"Filas: {stats['row_count']}, Tamaño: {stats['total_size']}")
for col in stats["columns"]:
    print(f"  {col['name']}: {col['type']} (nullable={col['nullable']})")
```

## Capacidad 4 — Plan de ejecución de un query (sin ejecutarlo)

```python
plan = client.explain_query("SELECT * FROM ventas WHERE anio = 2026")
print(f"Costo estimado: {plan['query_cost']}")
print(plan["plan"])  # árbol completo de EXPLAIN FORMAT=JSON
```

`explain_query` usa `EXPLAIN FORMAT=JSON` y solo acepta sentencias `SELECT`: el query nunca se ejecuta ni modifica datos.

## Manejo de errores

```python
from ruvic_mysql_connector import (
    MysqlAuthError, MysqlDataError, MysqlNetworkError,
)

try:
    rows = client.read_table("pedidos")
except MysqlAuthError:
    print("Credenciales inválidas — revisa la configuración del conector")
except MysqlNetworkError:
    print("No se pudo alcanzar el servidor — revisa host/puerto/red")
except MysqlDataError as e:
    print(f"Error de datos: {e}")  # ej. la tabla no existe
```

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_MYSQL_*` (el constructor de `MysqlClient` ya lo hace).
2. Nunca imprimas `RUVIC_MYSQL_PASSWORD` en logs ni en la salida.
3. La librería es de SOLO LECTURA: no intentes INSERT/UPDATE/DELETE con ella.
4. Usa `limit` razonable en `read_table` (default 100) para no traer tablas enteras.
5. Para analizar rendimiento de un query usa `explain_query`, nunca lo ejecutes directamente.
