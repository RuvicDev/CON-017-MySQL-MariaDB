# Conector MySQL / MariaDB (CON-017)

Conector Ruvic de solo lectura para MySQL y MariaDB. Permite listar tablas,
leer datos con límite, obtener estadísticas de tablas y analizar el plan de
ejecución de un query sin ejecutarlo.

## Instalación

```bash
pip install git+https://github.com/Dgirto/conector-mysql.git#subdirectory=lib
```

Python 3.10+. Dependencia única: `mysql-connector-python>=8.0,<9.0`.

## Permisos requeridos en el servidor

Crea un usuario dedicado de solo lectura (no reutilizar un usuario admin o
de aplicación):

```sql
CREATE USER 'ruvic_reader'@'%' IDENTIFIED BY 'CAMBIA_ESTA_CONTRASEÑA';
GRANT SELECT ON tu_base_de_datos.* TO 'ruvic_reader'@'%';
FLUSH PRIVILEGES;
```

- `SELECT` sobre el/los esquemas a exponer: necesario para `db.read`,
  `db.stats` y `db.explain`.
- Acceso de lectura a `information_schema`: disponible para cualquier
  usuario autenticado sobre los objetos que puede ver; no requiere GRANT
  adicional.
- No se otorgan permisos de escritura ni administración.

## Variables de entorno (`RUVIC_MYSQL_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_MYSQL_HOST` | Sí | Host del servidor |
| `RUVIC_MYSQL_PORT` | No (default `3306`) | Puerto |
| `RUVIC_MYSQL_DATABASE` | Sí | Base de datos a consultar |
| `RUVIC_MYSQL_USERNAME` | Sí | Usuario |
| `RUVIC_MYSQL_PASSWORD` | Sí | Contraseña |
| `RUVIC_MYSQL_CONNECT_TIMEOUT` | No (default `10`) | Timeout de conexión en segundos |

## Pruebas locales

Con Docker:

```bash
docker run -d --name mysql-test \
  -e MYSQL_ROOT_PASSWORD=root123 \
  -e MYSQL_DATABASE=demo \
  -p 3306:3306 \
  mysql:8.0

docker exec -i mysql-test mysql -uroot -proot123 demo <<'SQL'
CREATE TABLE clientes (id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(100), ciudad VARCHAR(100));
INSERT INTO clientes (nombre, ciudad) VALUES ('ACME', 'Bogotá'), ('Globex', 'Medellín');
SQL
```

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_MYSQL_HOST=localhost
export RUVIC_MYSQL_PORT=3306
export RUVIC_MYSQL_DATABASE=demo
export RUVIC_MYSQL_USERNAME=root
export RUVIC_MYSQL_PASSWORD=root123

python test_connection.py
```

Prueba también los casos de error (contraseña incorrecta, host inalcanzable,
tabla inexistente) y verifica que los mensajes sean claros.

## Notas de integración

- La sesión se abre en modo `SET SESSION TRANSACTION READ ONLY` como
  segunda barrera de seguridad (la primera es que el usuario de BD solo
  tiene `SELECT`). En MariaDB/MySQL muy antiguos donde esta sentencia no
  exista, el conector solo emite `SELECT`/`EXPLAIN` de todas formas.
- `explain_query` valida que el statement sea un único `SELECT` (rechaza
  `;` múltiples) y usa `EXPLAIN FORMAT=JSON` — nunca ejecuta el query.
- Sin límites de tasa conocidos del lado del conector; los límites de
  conexiones concurrentes dependen de la configuración (`max_connections`)
  del servidor MySQL/MariaDB.
