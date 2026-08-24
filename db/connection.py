import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager

from config import (
    AUTH_USERS_FILE,
    DATA_DIR,
    LEGACY_AUTH_USERS_FILE,
    LEGACY_ROOT_DATA_DIR,
    ROOT_DIR,
    ensure_private_dirs,
)

LEGACY_DB_NAME = DATA_DIR / "finanzas.db"
DB_LOCK = threading.RLock()
AUTH_LOCK = threading.RLock()

BROKERS_INICIALES = ["MyInvestor", "Trade Republic", "XTB"]
CUENTAS_INICIALES = ["BBVA", "Santander", "Revolut", "Efectivo"]
SECTORES_INICIALES = ["Balance inicial", "Sueldo", "Restaurantes", "Compras", "Transporte", "Otros"]
TIPOS_ACTIVO_INICIALES = [
    "Renta variable",
    "Renta fija",
    "Activo refugio",
    "Inmobiliario",
    "Criptoactivo",
    "Efectivo y monetarios",
    "Otros",
]

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
PASSWORD_MIN_LENGTH = 8
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 5 * 60
FAILED_LOGINS = {}


def normalize_username(username):
    return (username or "").strip().lower()


def validate_username(username):
    username = normalize_username(username)
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("El usuario debe tener 3-32 caracteres y solo letras, números o guion bajo.")
    return username


def validate_password(password):
    password = password or ""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if not any(char.isupper() for char in password):
        raise ValueError("La contraseña debe tener al menos una mayúscula.")
    if not any(char.isdigit() for char in password):
        raise ValueError("La contraseña debe tener al menos un número.")
    return password


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    ).hex()
    return salt, password_hash


def ensure_data_dir():
    ensure_private_dirs()


def migrate_database_files_to_data():
    ensure_data_dir()
    for source_dir in (ROOT_DIR, LEGACY_ROOT_DATA_DIR):
        if not source_dir.exists():
            continue
        for path in source_dir.glob("finanzas*.db*"):
            if not path.is_file():
                continue
            target = DATA_DIR / path.name
            if path.resolve() == target.resolve() or target.exists():
                continue
            try:
                shutil.move(str(path), str(target))
            except PermissionError:
                if target.exists():
                    continue
                raise


def user_db_path(username):
    username = validate_username(username)
    ensure_data_dir()
    return DATA_DIR / f"finanzas_{username}.db"


def current_username():
    try:
        from nicegui import app

        username = app.storage.user.get("username")
    except RuntimeError:
        username = None
    username = normalize_username(username)
    if not username:
        raise RuntimeError("No hay un usuario autenticado para abrir la base de datos.")
    if username not in load_auth_users():
        raise RuntimeError("El usuario autenticado ya no existe.")
    return username


@contextmanager
def conectar_db():
    username = current_username()
    with DB_LOCK:
        conn = sqlite3.connect(user_db_path(username), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = TRUNCATE")
        conn.execute("PRAGMA synchronous = NORMAL")
        cursor = conn.cursor()
        init_schema(cursor)
        ensure_schema_compatible(cursor, username)
        conn.commit()
        try:
            yield conn
        finally:
            conn.close()


@contextmanager
def conectar_db_usuario(username):
    with DB_LOCK:
        conn = sqlite3.connect(user_db_path(username), timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = TRUNCATE")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
        finally:
            conn.close()


def init_auth_db():
    ensure_private_dirs()
    if not AUTH_USERS_FILE.exists() and LEGACY_AUTH_USERS_FILE.exists():
        try:
            shutil.move(str(LEGACY_AUTH_USERS_FILE), str(AUTH_USERS_FILE))
        except PermissionError:
            if not AUTH_USERS_FILE.exists():
                raise
    if not AUTH_USERS_FILE.exists():
        save_auth_users({})


def load_auth_users():
    init_auth_db()
    try:
        return json.loads(AUTH_USERS_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"El archivo de usuarios esta corrupto: {AUTH_USERS_FILE}. "
            "Corrigelo o restaura una copia antes de arrancar la app."
        ) from exc


def save_auth_users(users):
    AUTH_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = AUTH_USERS_FILE.with_suffix(".json.tmp")
    content = json.dumps(users, indent=2, sort_keys=True)
    temp_path.write_text(content, encoding="utf-8")
    try:
        os.replace(temp_path, AUTH_USERS_FILE)
    except PermissionError:
        AUTH_USERS_FILE.write_text(content, encoding="utf-8")
        try:
            temp_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def login_lock_key(username):
    return normalize_username(username) or "__empty__"


def is_login_locked(username):
    key = login_lock_key(username)
    record = FAILED_LOGINS.get(key)
    if not record:
        return False
    if record["locked_until"] <= time.monotonic():
        FAILED_LOGINS.pop(key, None)
        return False
    return True


def register_failed_login(username):
    key = login_lock_key(username)
    now = time.monotonic()
    record = FAILED_LOGINS.get(key, {"count": 0, "locked_until": 0})
    if record["locked_until"] > now:
        return
    record["count"] += 1
    if record["count"] >= MAX_LOGIN_ATTEMPTS:
        record["locked_until"] = now + LOGIN_LOCK_SECONDS
        record["count"] = 0
    FAILED_LOGINS[key] = record


def clear_failed_logins(username):
    FAILED_LOGINS.pop(login_lock_key(username), None)


def create_user(username, password):
    username = validate_username(username)
    password = validate_password(password)
    salt, password_hash = hash_password(password)
    with AUTH_LOCK:
        users = load_auth_users()
        if username in users:
            raise ValueError("Ese usuario ya existe.")
        users[username] = {
            "salt": salt,
            "password_hash": password_hash,
        }
        save_auth_users(users)
    init_user_db(username, seed_defaults=True)
    return username


def set_user_password(username, password):
    username = validate_username(username)
    password = validate_password(password)
    salt, password_hash = hash_password(password)
    with AUTH_LOCK:
        users = load_auth_users()
        if username not in users:
            raise ValueError("Ese usuario no existe.")
        users[username] = {
            "salt": salt,
            "password_hash": password_hash,
        }
        save_auth_users(users)
    clear_failed_logins(username)


def verify_user(username, password):
    username = normalize_username(username)
    with AUTH_LOCK:
        if is_login_locked(username):
            return None
        users = load_auth_users()
        user = users.get(username)
        if user is None:
            register_failed_login(username)
            return None
    salt = user["salt"]
    expected_hash = user["password_hash"]
    _, actual_hash = hash_password(password or "", salt)
    if hmac.compare_digest(actual_hash, expected_hash):
        clear_failed_logins(username)
        return username
    register_failed_login(username)
    return None


def list_users():
    return sorted(load_auth_users())


def init_schema(cursor):
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            fecha_registro TEXT,
            tipo TEXT,
            descripcion TEXT,
            cuenta TEXT,
            sector TEXT,
            importe REAL,
            usuario TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS inversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            inversion TEXT,
            dinero_inicial REAL,
            valor_actual REAL,
            aplicacion TEXT,
            tipo_activo TEXT DEFAULT 'Sin clasificar',
            operacion_id INTEGER,
            usuario TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS historico_inversiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            inversion TEXT,
            precio_compra REAL,
            precio_venta REAL,
            comisiones REAL DEFAULT 0,
            aplicacion TEXT,
            tipo_activo TEXT DEFAULT 'Sin clasificar',
            operacion_id INTEGER,
            usuario TEXT
        )"""
    )
    cursor.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_historico_inversiones_operacion_usuario
           ON historico_inversiones (operacion_id, usuario)"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS operaciones_inversion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            fecha_registro TEXT,
            inversion TEXT,
            tipo TEXT,
            importe REAL,
            unidades REAL,
            precio_unitario REAL,
            comisiones REAL DEFAULT 0,
            cuenta TEXT,
            transaccion_id INTEGER,
            notas TEXT,
            usuario TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS situacion_global (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cantidad REAL,
            ubicacion TEXT,
            aplicacion TEXT,
            tipo TEXT,
            usuario TEXT
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS brokers (
            nombre TEXT PRIMARY KEY
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS cuentas (
            nombre TEXT PRIMARY KEY
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS sectores (
            nombre TEXT PRIMARY KEY
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS tipos_activo (
            nombre TEXT PRIMARY KEY
        )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS activos (
            inversion TEXT,
            aplicacion TEXT,
            tipo_activo TEXT DEFAULT 'Sin clasificar',
            usuario TEXT,
            PRIMARY KEY (inversion, usuario)
        )"""
    )
    ensure_activos_cotizacion_table(cursor)
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS preferencias_usuario (
            usuario TEXT,
            clave TEXT,
            valor TEXT,
            PRIMARY KEY (usuario, clave)
        )"""
    )
    ensure_transaction_indexes(cursor)


def seed_default_catalogs(cursor):
    cursor.executemany(
        "INSERT OR IGNORE INTO brokers (nombre) VALUES (?)",
        [(nombre,) for nombre in BROKERS_INICIALES],
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)",
        [(nombre,) for nombre in CUENTAS_INICIALES],
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO sectores (nombre) VALUES (?)",
        [(nombre,) for nombre in SECTORES_INICIALES],
    )
    cursor.executemany(
        "INSERT OR IGNORE INTO tipos_activo (nombre) VALUES (?)",
        [(nombre,) for nombre in TIPOS_ACTIVO_INICIALES],
    )


def ensure_column(cursor, table, column, definition):
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def ensure_activos_cotizacion_table(cursor):
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS activos_cotizacion (
            usuario TEXT,
            inversion TEXT,
            ticker_yahoo TEXT,
            divisa_cotizacion TEXT,
            divisa_valoracion TEXT DEFAULT 'EUR',
            auto_update_enabled INTEGER DEFAULT 1,
            logo_url TEXT,
            PRIMARY KEY (usuario, inversion)
        )"""
    )
    ensure_column(cursor, "activos_cotizacion", "divisa_cotizacion", "TEXT")
    ensure_column(cursor, "activos_cotizacion", "divisa_valoracion", "TEXT DEFAULT 'EUR'")
    ensure_column(cursor, "activos_cotizacion", "auto_update_enabled", "INTEGER DEFAULT 1")
    ensure_column(cursor, "activos_cotizacion", "logo_url", "TEXT")
    cursor.execute(
        """UPDATE activos_cotizacion
           SET divisa_valoracion = 'EUR'
           WHERE divisa_valoracion IS NULL OR TRIM(divisa_valoracion) = ''"""
    )
    cursor.execute(
        """UPDATE activos_cotizacion
           SET auto_update_enabled = 1
           WHERE auto_update_enabled IS NULL"""
    )


def ensure_fecha_registro_triggers(cursor):
    cursor.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_transacciones_fecha_registro_ai
           AFTER INSERT ON transacciones
           FOR EACH ROW
           WHEN NEW.fecha_registro IS NULL OR NEW.fecha_registro = ''
           BEGIN
               UPDATE transacciones
               SET fecha_registro = date('now', 'localtime')
               WHERE id = NEW.id;
           END"""
    )
    cursor.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_operaciones_inversion_fecha_registro_ai
           AFTER INSERT ON operaciones_inversion
           FOR EACH ROW
           WHEN NEW.fecha_registro IS NULL OR NEW.fecha_registro = ''
           BEGIN
               UPDATE operaciones_inversion
               SET fecha_registro = date('now', 'localtime')
               WHERE id = NEW.id;
           END"""
    )


def ensure_transaction_indexes(cursor):
    cursor.execute(
        """CREATE INDEX IF NOT EXISTS idx_transacciones_usuario_fecha_id
           ON transacciones (usuario, fecha, id)"""
    )
    cursor.execute(
        """CREATE INDEX IF NOT EXISTS idx_transacciones_usuario_fecha_registro_id
           ON transacciones (usuario, fecha_registro, id)"""
    )
    cursor.execute(
        """CREATE INDEX IF NOT EXISTS idx_transacciones_usuario_importe_id
           ON transacciones (usuario, importe, id)"""
    )
    cursor.execute(
        """CREATE INDEX IF NOT EXISTS idx_transacciones_usuario_tipo_cuenta_sector
           ON transacciones (usuario, tipo, cuenta, sector)"""
    )


def sync_investment_liquidity_accounts(cursor, username):
    cursor.execute(
        """INSERT OR IGNORE INTO cuentas (nombre)
           SELECT DISTINCT aplicacion
           FROM inversiones
           WHERE usuario = ?
             AND aplicacion IS NOT NULL
             AND TRIM(aplicacion) != ''""",
        (username,),
    )
    cursor.execute(
        """UPDATE operaciones_inversion
           SET cuenta = (
               SELECT activos.aplicacion
               FROM activos
               WHERE activos.usuario = operaciones_inversion.usuario
                 AND activos.inversion = operaciones_inversion.inversion
           )
           WHERE usuario = ?
             AND EXISTS (
                 SELECT 1
                 FROM activos
                 WHERE activos.usuario = operaciones_inversion.usuario
                   AND activos.inversion = operaciones_inversion.inversion
                   AND activos.aplicacion IS NOT NULL
                   AND TRIM(activos.aplicacion) != ''
             )""",
        (username,),
    )
    cursor.execute(
        """UPDATE transacciones
           SET cuenta = (
               SELECT operaciones_inversion.cuenta
               FROM operaciones_inversion
               WHERE operaciones_inversion.usuario = transacciones.usuario
                 AND operaciones_inversion.transaccion_id = transacciones.id
           )
           WHERE usuario = ?
             AND EXISTS (
                 SELECT 1
                 FROM operaciones_inversion
                 WHERE operaciones_inversion.usuario = transacciones.usuario
                   AND operaciones_inversion.transaccion_id = transacciones.id
                   AND operaciones_inversion.cuenta IS NOT NULL
                   AND TRIM(operaciones_inversion.cuenta) != ''
             )""",
        (username,),
    )


def ensure_schema_compatible(cursor, username):
    ensure_column(cursor, "transacciones", "usuario", "TEXT")
    ensure_column(cursor, "transacciones", "fecha_registro", "TEXT")
    ensure_column(cursor, "inversiones", "tipo_activo", "TEXT DEFAULT 'Sin clasificar'")
    ensure_column(cursor, "inversiones", "operacion_id", "INTEGER")
    ensure_column(cursor, "inversiones", "usuario", "TEXT")
    ensure_column(cursor, "historico_inversiones", "tipo_activo", "TEXT DEFAULT 'Sin clasificar'")
    ensure_column(cursor, "historico_inversiones", "operacion_id", "INTEGER")
    ensure_column(cursor, "historico_inversiones", "comisiones", "REAL DEFAULT 0")
    ensure_column(cursor, "historico_inversiones", "usuario", "TEXT")
    ensure_column(cursor, "operaciones_inversion", "usuario", "TEXT")
    ensure_column(cursor, "operaciones_inversion", "notas", "TEXT")
    ensure_column(cursor, "operaciones_inversion", "fecha_registro", "TEXT")
    ensure_column(cursor, "situacion_global", "usuario", "TEXT")
    ensure_column(cursor, "activos", "usuario", "TEXT")
    ensure_activos_cotizacion_table(cursor)
    ensure_fecha_registro_triggers(cursor)
    ensure_transaction_indexes(cursor)
    cursor.execute(
        """UPDATE transacciones
           SET fecha_registro = fecha
           WHERE fecha_registro IS NULL OR fecha_registro = ''"""
    )
    cursor.execute(
        """UPDATE operaciones_inversion
           SET fecha_registro = fecha
           WHERE fecha_registro IS NULL OR fecha_registro = ''"""
    )
    cursor.execute(
        """UPDATE historico_inversiones
           SET comisiones = COALESCE((
               SELECT operaciones_inversion.comisiones
               FROM operaciones_inversion
               WHERE operaciones_inversion.id = historico_inversiones.operacion_id
                 AND operaciones_inversion.usuario = historico_inversiones.usuario
           ), 0)
           WHERE usuario = ?
             AND (comisiones IS NULL OR comisiones = 0)
             AND operacion_id IS NOT NULL""",
        (username,),
    )
    cursor.execute(
        """UPDATE inversiones
           SET operacion_id = (
               SELECT historico_inversiones.operacion_id
               FROM historico_inversiones
               JOIN operaciones_inversion
                 ON operaciones_inversion.id = historico_inversiones.operacion_id
                AND operaciones_inversion.usuario = historico_inversiones.usuario
               WHERE historico_inversiones.usuario = inversiones.usuario
                 AND historico_inversiones.inversion = inversiones.inversion
                 AND historico_inversiones.fecha = inversiones.fecha
                 AND operaciones_inversion.tipo = 'Venta'
               ORDER BY historico_inversiones.id DESC
               LIMIT 1
           )
           WHERE usuario = ?
             AND operacion_id IS NULL
             AND EXISTS (
                 SELECT 1
                 FROM historico_inversiones
                 JOIN operaciones_inversion
                   ON operaciones_inversion.id = historico_inversiones.operacion_id
                  AND operaciones_inversion.usuario = historico_inversiones.usuario
                 WHERE historico_inversiones.usuario = inversiones.usuario
                   AND historico_inversiones.inversion = inversiones.inversion
                   AND historico_inversiones.fecha = inversiones.fecha
                   AND operaciones_inversion.tipo = 'Venta'
             )""",
        (username,),
    )
    ensure_activos_name_key(cursor, username)
    delete_orphan_assets(cursor, username)
    sync_investment_liquidity_accounts(cursor, username)


def delete_orphan_assets(cursor, username):
    cursor.execute(
        """DELETE FROM activos
           WHERE usuario = ?
             AND NOT EXISTS (
                 SELECT 1 FROM inversiones
                 WHERE inversiones.usuario = activos.usuario
                   AND inversiones.inversion = activos.inversion
             )
             AND NOT EXISTS (
                 SELECT 1 FROM operaciones_inversion
                 WHERE operaciones_inversion.usuario = activos.usuario
                   AND operaciones_inversion.inversion = activos.inversion
             )""",
        (username,),
    )
    cursor.execute(
        """DELETE FROM activos_cotizacion
           WHERE usuario = ?
             AND NOT EXISTS (
                 SELECT 1 FROM activos
                 WHERE activos.usuario = activos_cotizacion.usuario
                   AND activos.inversion = activos_cotizacion.inversion
             )""",
        (username,),
    )


def ensure_activos_name_key(cursor, username):
    pk_columns = [
        row[1]
        for row in sorted(
            cursor.execute("PRAGMA table_info(activos)").fetchall(),
            key=lambda row: row[5],
        )
        if row[5]
    ]
    if pk_columns == ["inversion", "usuario"]:
        return

    cursor.execute("ALTER TABLE activos RENAME TO activos_old")
    cursor.execute(
        """CREATE TABLE activos (
            inversion TEXT,
            aplicacion TEXT,
            tipo_activo TEXT DEFAULT 'Sin clasificar',
            usuario TEXT,
            PRIMARY KEY (inversion, usuario)
        )"""
    )
    cursor.execute(
        """INSERT OR IGNORE INTO activos (inversion, aplicacion, tipo_activo, usuario)
           SELECT a.inversion,
                  COALESCE(a.aplicacion, ''),
                  COALESCE(NULLIF(a.tipo_activo, ''), 'Sin clasificar'),
                  COALESCE(NULLIF(a.usuario, ''), ?)
           FROM activos_old a
           JOIN (
               SELECT inversion,
                      COALESCE(NULLIF(usuario, ''), ?) AS usuario,
                      MAX(rowid) AS rowid
               FROM activos_old
               WHERE inversion IS NOT NULL
                 AND TRIM(inversion) != ''
               GROUP BY inversion, COALESCE(NULLIF(usuario, ''), ?)
           ) ultimos ON ultimos.rowid = a.rowid
           WHERE a.inversion IS NOT NULL
             AND TRIM(a.inversion) != ''""",
        (username, username, username),
    )
    cursor.execute("DROP TABLE activos_old")


def seed_catalogs_from_data(cursor):
    cursor.execute(
        """INSERT OR IGNORE INTO cuentas (nombre)
           SELECT DISTINCT cuenta FROM transacciones
           WHERE cuenta IS NOT NULL AND TRIM(cuenta) != ''"""
    )
    cursor.execute(
        """INSERT OR IGNORE INTO sectores (nombre)
           SELECT DISTINCT sector FROM transacciones
           WHERE sector IS NOT NULL AND TRIM(sector) != ''"""
    )
    cursor.execute(
        """INSERT OR IGNORE INTO brokers (nombre)
           SELECT DISTINCT aplicacion FROM inversiones
           WHERE aplicacion IS NOT NULL AND TRIM(aplicacion) != ''"""
    )
    cursor.execute(
        """INSERT OR IGNORE INTO tipos_activo (nombre)
           SELECT DISTINCT tipo_activo FROM inversiones
           WHERE tipo_activo IS NOT NULL AND TRIM(tipo_activo) != ''"""
    )


def seed_assets_from_investments(cursor, username):
    delete_orphan_assets(cursor, username)
    cursor.execute(
        """INSERT OR IGNORE INTO activos (inversion, aplicacion, tipo_activo, usuario)
           SELECT inv.inversion,
                  COALESCE(inv.aplicacion, ''),
                  COALESCE(NULLIF(inv.tipo_activo, ''), 'Sin clasificar'),
                  ?
           FROM inversiones inv
           JOIN (
               SELECT inversion, MAX(fecha || printf('%012d', id)) AS orden
               FROM inversiones
               WHERE usuario = ?
                 AND inversion IS NOT NULL
                 AND TRIM(inversion) != ''
               GROUP BY inversion
            ) ultimos
              ON ultimos.inversion = inv.inversion
             AND ultimos.orden = inv.fecha || printf('%012d', inv.id)
            WHERE inv.usuario = ?""",
        (username, username, username),
    )


def init_user_db(username, seed_defaults=False):
    username = validate_username(username)
    with conectar_db_usuario(username) as conn:
        cursor = conn.cursor()
        init_schema(cursor)
        if seed_defaults:
            seed_default_catalogs(cursor)
        ensure_schema_compatible(cursor, username)
        cursor.execute("UPDATE transacciones SET usuario = ? WHERE usuario IS NULL OR usuario = ''", (username,))
        cursor.execute("UPDATE inversiones SET usuario = ? WHERE usuario IS NULL OR usuario = ''", (username,))
        cursor.execute(
            "UPDATE historico_inversiones SET usuario = ? WHERE usuario IS NULL OR usuario = ''",
            (username,),
        )
        cursor.execute(
            "UPDATE operaciones_inversion SET usuario = ? WHERE usuario IS NULL OR usuario = ''",
            (username,),
        )
        cursor.execute("UPDATE situacion_global SET usuario = ? WHERE usuario IS NULL OR usuario = ''", (username,))
        cursor.execute("UPDATE activos SET usuario = ? WHERE usuario IS NULL OR usuario = ''", (username,))
        seed_catalogs_from_data(cursor)
        seed_assets_from_investments(cursor, username)
        sync_investment_liquidity_accounts(cursor, username)
        conn.commit()


def legacy_has_user_column(cursor, table):
    return "usuario" in {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}


def copy_legacy_user_data(source_cursor, target_cursor, legacy_user, target_user):
    tx_has_user = legacy_has_user_column(source_cursor, "transacciones")
    inv_has_user = legacy_has_user_column(source_cursor, "inversiones")
    global_has_user = legacy_has_user_column(source_cursor, "situacion_global")

    tx_query = "SELECT fecha, tipo, descripcion, cuenta, sector, importe FROM transacciones"
    tx_params = ()
    if tx_has_user:
        tx_query += " WHERE usuario = ?"
        tx_params = (legacy_user,)
    target_cursor.executemany(
        """INSERT INTO transacciones
           (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(row[0], row[0], *row[1:], target_user) for row in source_cursor.execute(tx_query, tx_params).fetchall()],
    )

    inv_query = "SELECT fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo FROM inversiones"
    inv_params = ()
    if inv_has_user:
        inv_query += " WHERE usuario = ?"
        inv_params = (legacy_user,)
    target_cursor.executemany(
        """INSERT INTO inversiones
           (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(*row, target_user) for row in source_cursor.execute(inv_query, inv_params).fetchall()],
    )

    global_query = "SELECT fecha, cantidad, ubicacion, aplicacion, tipo FROM situacion_global"
    global_params = ()
    if global_has_user:
        global_query += " WHERE usuario = ?"
        global_params = (legacy_user,)
    target_cursor.executemany(
        """INSERT INTO situacion_global
           (fecha, cantidad, ubicacion, aplicacion, tipo, usuario)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(*row, target_user) for row in source_cursor.execute(global_query, global_params).fetchall()],
    )


def user_db_has_data(username):
    path = user_db_path(username)
    if not path.exists():
        return False
    with sqlite3.connect(path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        if not {"transacciones", "inversiones"} <= tables:
            return False
        tx_count = conn.execute("SELECT COUNT(*) FROM transacciones").fetchone()[0]
        inv_count = conn.execute("SELECT COUNT(*) FROM inversiones").fetchone()[0]
    return tx_count > 0 or inv_count > 0


def migrate_legacy_user(legacy_user, target_user):
    if user_db_has_data(target_user) or not LEGACY_DB_NAME.exists():
        return
    init_user_db(target_user)
    with sqlite3.connect(LEGACY_DB_NAME) as source, conectar_db_usuario(target_user) as target:
        source_cursor = source.cursor()
        target_cursor = target.cursor()
        copy_legacy_user_data(source_cursor, target_cursor, legacy_user, target_user)
        seed_catalogs_from_data(target_cursor)
        target.commit()


def seed_demo_data():
    if user_db_has_data("demo"):
        return
    init_user_db("demo")
    demo_transacciones = [
        ("2026-01-01", "Ingreso", "Balance inicial", "Cuenta demo", "Balance inicial", 3200.00),
        ("2026-01-30", "Ingreso", "Nómina enero", "Cuenta demo", "Sueldo", 2300.00),
        ("2026-02-28", "Ingreso", "Nómina febrero", "Cuenta demo", "Sueldo", 2300.00),
        ("2026-03-31", "Ingreso", "Nómina marzo", "Cuenta demo", "Sueldo", 2300.00),
        ("2026-04-30", "Ingreso", "Nómina abril", "Cuenta demo", "Sueldo", 2300.00),
        ("2026-05-31", "Ingreso", "Nómina mayo", "Cuenta demo", "Sueldo", 2300.00),
        ("2026-06-15", "Ingreso", "Venta segunda mano", "Revolut Demo", "Ingresos extra", 180.00),
        ("2026-02-03", "Gasto", "Alquiler", "Cuenta demo", "Vivienda", -850.00),
        ("2026-03-03", "Gasto", "Alquiler", "Cuenta demo", "Vivienda", -850.00),
        ("2026-04-03", "Gasto", "Alquiler", "Cuenta demo", "Vivienda", -850.00),
        ("2026-05-03", "Gasto", "Alquiler", "Cuenta demo", "Vivienda", -850.00),
        ("2026-06-03", "Gasto", "Alquiler", "Cuenta demo", "Vivienda", -850.00),
        ("2026-06-05", "Gasto", "Supermercado", "Tarjeta demo", "Compras", -126.40),
        ("2026-06-07", "Gasto", "Restaurante", "Tarjeta demo", "Comidas fuera", -42.80),
        ("2026-06-08", "Gasto", "Metro y bus", "Tarjeta demo", "Transporte", -31.20),
        ("2026-06-10", "Gasto", "Gimnasio", "Cuenta demo", "Salud", -39.99),
        ("2026-06-12", "Gasto", "Suscripciones", "Tarjeta demo", "Ocio", -24.98),
        ("2026-06-16", "Gasto", "Aportación inversión", "Cuenta demo", "Inversiones", -250.00),
    ]
    demo_inversiones = [
        ("2026-04-01", "ETF MSCI World Demo", 1200.00, 1235.50, "Trade Republic", "Renta variable"),
        ("2026-04-01", "Bono Gobierno Demo", 600.00, 603.20, "Openbank Demo", "Renta fija"),
        ("2026-04-01", "Oro físico Demo", 350.00, 362.40, "Trade Republic", "Activo refugio"),
        ("2026-05-01", "ETF MSCI World Demo", 1400.00, 1468.10, "Trade Republic", "Renta variable"),
        ("2026-05-01", "Bono Gobierno Demo", 600.00, 608.50, "Openbank Demo", "Renta fija"),
        ("2026-05-01", "Oro físico Demo", 350.00, 371.80, "Trade Republic", "Activo refugio"),
        ("2026-06-16", "ETF MSCI World Demo", 1650.00, 1715.30, "Trade Republic", "Renta variable"),
        ("2026-06-16", "Bono Gobierno Demo", 600.00, 612.90, "Openbank Demo", "Renta fija"),
        ("2026-06-16", "Oro físico Demo", 350.00, 384.10, "Trade Republic", "Activo refugio"),
        ("2026-06-16", "Bitcoin Demo", 150.00, 168.70, "Revolut", "Criptoactivo"),
    ]
    with conectar_db_usuario("demo") as conn:
        cursor = conn.cursor()
        cursor.executemany(
            """INSERT INTO transacciones
               (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'demo')""",
            [(row[0], row[0], *row[1:]) for row in demo_transacciones],
        )
        cursor.executemany(
            """INSERT INTO inversiones
               (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?, ?, ?, 'demo')""",
            demo_inversiones,
        )
        seed_catalogs_from_data(cursor)
        conn.commit()


def init_db():
    migrate_database_files_to_data()
    init_auth_db()
    users = list_users()
    if "cesar" in users:
        migrate_legacy_user("personal", "cesar")
    if "demo" in users:
        migrate_legacy_user("demo", "demo")
        seed_demo_data()
    for username in users:
        init_user_db(username)
    from db.backups import create_due_backups

    create_due_backups()
