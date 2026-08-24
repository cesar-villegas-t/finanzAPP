import json
from datetime import date, timedelta

import pandas as pd

from db.connection import conectar_db

TABLAS_CON_USUARIO = {
    "transacciones",
    "inversiones",
    "historico_inversiones",
    "operaciones_inversion",
    "situacion_global",
    "activos",
    "activos_cotizacion",
}
CATALOGOS_PERMITIDOS = {"brokers", "tipos_activo", "cuentas", "sectores"}
TABLAS_PERMITIDAS = TABLAS_CON_USUARIO | CATALOGOS_PERMITIDOS
TIPOS_OPERACION_INVERSION = {"Compra", "Venta"}
TIPOS_MOVIMIENTO = {"Ingreso", "Gasto", "Traspaso"}
COLUMNAS_FILTRO_MOVIMIENTOS = {"cuenta", "sector"}
ORDEN_MOVIMIENTOS_SQL = {
    "Fecha": "fecha",
    "Fecha de registro": "COALESCE(NULLIF(fecha_registro, ''), fecha)",
    "Importe": "importe",
}
IMPORTE_EPSILON = 0.005
UNIDADES_EPSILON = 1e-9


def _fecha_registro_actual():
    return date.today().isoformat()


def _formato_numero_es(valor, decimales=2, sufijo="", trim_zeros=False):
    texto = format(float(valor or 0), f",.{decimales}f").replace(",", "_").replace(".", ",").replace("_", ".")
    if trim_zeros and "," in texto:
        texto = texto.rstrip("0").rstrip(",")
    return f"{texto}{sufijo}"


def ejecutar_query(query, params=()):
    with conectar_db() as conn:
        conn.execute(query, params)
        conn.commit()


def cargar_preferencia_usuario(clave, usuario, default=None):
    with conectar_db() as conn:
        row = conn.execute(
            """SELECT valor
               FROM preferencias_usuario
               WHERE usuario = ?
                 AND clave = ?""",
            (usuario, clave),
        ).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return default


def guardar_preferencia_usuario(clave, valor, usuario):
    valor_json = json.dumps(valor, ensure_ascii=False, sort_keys=True)
    with conectar_db() as conn:
        conn.execute(
            """INSERT INTO preferencias_usuario (usuario, clave, valor)
               VALUES (?, ?, ?)
               ON CONFLICT(usuario, clave) DO UPDATE SET
                   valor = excluded.valor""",
            (usuario, clave, valor_json),
        )
        conn.commit()


def cargar_datos(tabla, usuario=None):
    if tabla not in TABLAS_PERMITIDAS:
        raise ValueError("Tabla no válida")
    with conectar_db() as conn:
        if tabla in TABLAS_CON_USUARIO and usuario is not None:
            return pd.read_sql(f"SELECT * FROM {tabla} WHERE usuario = ?", conn, params=(usuario,))
        return pd.read_sql(f"SELECT * FROM {tabla}", conn)


def _normalizar_filtros_movimientos(filtros):
    filtros = filtros or {}
    tipos = [tipo for tipo in filtros.get("tipos", []) if tipo in TIPOS_MOVIMIENTO]
    cuentas = [str(cuenta).strip() for cuenta in filtros.get("cuentas", []) if str(cuenta or "").strip()]
    sectores = [str(sector).strip() for sector in filtros.get("sectores", []) if str(sector or "").strip()]
    orden = filtros.get("orden") if filtros.get("orden") in ORDEN_MOVIMIENTOS_SQL else "Fecha"
    direccion = "ASC" if filtros.get("direccion") == "Ascendente" else "DESC"
    return {
        "tipos": tipos or list(TIPOS_MOVIMIENTO),
        "cuentas": cuentas,
        "sectores": sectores,
        "orden": orden,
        "direccion": direccion,
    }


def _where_movimientos(usuario, filtros):
    filtros = _normalizar_filtros_movimientos(filtros)
    clauses = ["usuario = ?"]
    params = [usuario]
    for columna, valores in (("tipo", filtros["tipos"]), ("cuenta", filtros["cuentas"]), ("sector", filtros["sectores"])):
        if valores:
            placeholders = ", ".join("?" for _ in valores)
            clauses.append(f"{columna} IN ({placeholders})")
            params.extend(valores)
    return " AND ".join(clauses), params, filtros


def consultar_movimientos(usuario, filtros, limit=50, offset=0):
    where_sql, params, filtros = _where_movimientos(usuario, filtros)
    limit = max(1, int(limit or 50))
    offset = max(0, int(offset or 0))
    orden_sql = ORDEN_MOVIMIENTOS_SQL[filtros["orden"]]
    direccion = filtros["direccion"]
    query = f"""SELECT *
                FROM transacciones
                WHERE {where_sql}
                ORDER BY {orden_sql} {direccion}, id {direccion}
                LIMIT ? OFFSET ?"""
    with conectar_db() as conn:
        return pd.read_sql(query, conn, params=(*params, limit, offset))


def resumen_movimientos(usuario, filtros):
    where_sql, params, _ = _where_movimientos(usuario, filtros)
    with conectar_db() as conn:
        row = conn.execute(
            f"""SELECT COUNT(*), COALESCE(SUM(importe), 0)
                FROM transacciones
                WHERE {where_sql}""",
            params,
        ).fetchone()
    return int(row[0] or 0), float(row[1] or 0)


def opciones_filtro_movimientos(usuario, columna):
    if columna not in COLUMNAS_FILTRO_MOVIMIENTOS:
        raise ValueError("Columna de filtro no valida.")
    with conectar_db() as conn:
        rows = conn.execute(
            f"""SELECT DISTINCT {columna}
                FROM transacciones
                WHERE usuario = ?
                  AND {columna} IS NOT NULL
                  AND TRIM({columna}) != ''""",
            (usuario,),
        ).fetchall()
    return sorted({row[0].strip() for row in rows if row[0]}, key=str.lower)


def opciones_recientes_movimientos(usuario, columna, opciones_base, opcion_otro, excluir_tipos=None):
    if columna not in COLUMNAS_FILTRO_MOVIMIENTOS:
        raise ValueError("Columna de opciones no valida.")

    opciones = []
    vistos = set()
    for opcion in opciones_base:
        opcion = (opcion or "").strip()
        clave = opcion.lower()
        if opcion and clave not in vistos and opcion != opcion_otro:
            opciones.append(opcion)
            vistos.add(clave)

    exclude = [tipo for tipo in (excluir_tipos or []) if tipo in TIPOS_MOVIMIENTO]
    exclude_sql = ""
    exclude_params = []
    if exclude:
        exclude_sql = f" AND tipo NOT IN ({', '.join('?' for _ in exclude)})"
        exclude_params = exclude

    fecha_minima = (date.today() - timedelta(days=60)).isoformat()
    with conectar_db() as conn:
        historicos = conn.execute(
            f"""SELECT DISTINCT {columna}
                FROM transacciones
                WHERE usuario = ?
                  AND {columna} IS NOT NULL
                  AND TRIM({columna}) != ''
                  {exclude_sql}""",
            (usuario, *exclude_params),
        ).fetchall()
        recientes = conn.execute(
            f"""SELECT {columna}, COUNT(*) AS total
                FROM transacciones
                WHERE usuario = ?
                  AND fecha >= ?
                  AND {columna} IS NOT NULL
                  AND TRIM({columna}) != ''
                  {exclude_sql}
                GROUP BY {columna}""",
            (usuario, fecha_minima, *exclude_params),
        ).fetchall()

    for row in historicos:
        valor = (row[0] or "").strip()
        clave = valor.lower()
        if valor and clave not in vistos and valor != opcion_otro:
            opciones.append(valor)
            vistos.add(clave)
    counts = {(row[0] or "").strip(): int(row[1] or 0) for row in recientes}
    opciones = sorted(opciones, key=lambda nombre: (-counts.get(nombre, 0), nombre.lower()))
    opciones.append(opcion_otro)
    return opciones


def ultimo_traspaso_entre_cuentas_usuario(usuario):
    with conectar_db() as conn:
        rows = conn.execute(
            """SELECT fecha, id, descripcion, cuenta, importe
               FROM transacciones
               WHERE usuario = ?
                 AND tipo = 'Traspaso'
               ORDER BY fecha DESC, id DESC
               LIMIT 200""",
            (usuario,),
        ).fetchall()
    if not rows:
        return None, None

    salidas = [row for row in rows if float(row[4] or 0) < 0]
    for salida in salidas:
        descripcion = str(salida[2] or "")
        base = descripcion.removesuffix(" - salida")
        for entrada in rows:
            if (
                entrada[0] == salida[0]
                and float(entrada[4] or 0) > 0
                and str(entrada[2] or "") in {f"{base} - entrada", base}
            ):
                return salida[3], entrada[3]

    fecha_ultima = rows[0][0]
    mismo_dia = [row for row in rows if row[0] == fecha_ultima]
    salida = next((row for row in mismo_dia if float(row[4] or 0) < 0), None)
    entrada = next((row for row in mismo_dia if float(row[4] or 0) > 0), None)
    if salida and entrada:
        return salida[3], entrada[3]
    return None, None


def insertar_transaccion(fecha, tipo, descripcion, cuenta, sector, importe, usuario):
    fecha_registro = _fecha_registro_actual()
    with conectar_db() as conn:
        conn.execute("INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)", (cuenta,))
        conn.execute("INSERT OR IGNORE INTO sectores (nombre) VALUES (?)", (sector,))
        conn.execute(
            """INSERT INTO transacciones
               (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario),
        )
        conn.commit()


def insertar_transacciones_masivas(registros, usuario):
    fecha_registro = _fecha_registro_actual()
    filas = [
        (
            registro["fecha"],
            fecha_registro,
            registro["tipo"],
            registro["descripcion"],
            registro["cuenta"],
            registro["sector"],
            registro["importe"],
            usuario,
        )
        for registro in registros
    ]
    with conectar_db() as conn:
        conn.executemany(
            """INSERT INTO transacciones
               (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            filas,
        )
        conn.commit()
    return len(filas)


def insertar_traspaso(fecha, descripcion, cuenta_origen, cuenta_destino, importe, usuario):
    sector = "Traspaso entre cuentas"
    descripcion = (descripcion or "").strip() or f"Traspaso de {cuenta_origen} a {cuenta_destino}"
    importe = abs(float(importe))
    fecha_registro = _fecha_registro_actual()
    with conectar_db() as conn:
        conn.execute("INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)", (cuenta_origen,))
        conn.execute("INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)", (cuenta_destino,))
        conn.execute("INSERT OR IGNORE INTO sectores (nombre) VALUES (?)", (sector,))
        conn.executemany(
            """INSERT INTO transacciones
               (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    fecha,
                    fecha_registro,
                    "Traspaso",
                    f"{descripcion} - salida",
                    cuenta_origen,
                    sector,
                    -importe,
                    usuario,
                ),
                (
                    fecha,
                    fecha_registro,
                    "Traspaso",
                    f"{descripcion} - entrada",
                    cuenta_destino,
                    sector,
                    importe,
                    usuario,
                ),
            ],
        )
        conn.commit()


def existe_transaccion(fecha, tipo, descripcion, cuenta, sector, importe, usuario):
    with conectar_db() as conn:
        count = conn.execute(
            """SELECT COUNT(*)
               FROM transacciones
               WHERE fecha = ? AND tipo = ? AND descripcion = ? AND cuenta = ? AND sector = ? AND importe = ? AND usuario = ?""",
            (fecha, tipo, descripcion, cuenta, sector, importe, usuario),
        ).fetchone()[0]
    return count > 0


def actualizar_transaccion(movimiento_id, fecha, tipo, descripcion, cuenta, sector, importe, usuario):
    with conectar_db() as conn:
        vinculada = conn.execute(
            """SELECT COUNT(*)
               FROM operaciones_inversion
               WHERE transaccion_id = ?
                 AND usuario = ?""",
            (movimiento_id, usuario),
        ).fetchone()[0]
        if vinculada:
            raise ValueError("Esta transaccion esta vinculada a una operacion de inversion.")
        conn.execute("INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)", (cuenta,))
        conn.execute("INSERT OR IGNORE INTO sectores (nombre) VALUES (?)", (sector,))
        conn.execute(
            """UPDATE transacciones
               SET fecha = ?, tipo = ?, descripcion = ?, cuenta = ?, sector = ?, importe = ?
               WHERE id = ? AND usuario = ?""",
            (fecha, tipo, descripcion, cuenta, sector, importe, movimiento_id, usuario),
        )
        conn.commit()


def eliminar_transaccion(movimiento_id, usuario):
    with conectar_db() as conn:
        vinculada = conn.execute(
            """SELECT COUNT(*)
               FROM operaciones_inversion
               WHERE transaccion_id = ?
                 AND usuario = ?""",
            (movimiento_id, usuario),
        ).fetchone()[0]
        if vinculada:
            raise ValueError("Esta transaccion esta vinculada a una operacion de inversion.")
        conn.execute("DELETE FROM transacciones WHERE id = ? AND usuario = ?", (movimiento_id, usuario))
        conn.commit()


def _latest_snapshot_activo(conn, inversion, usuario, fecha=None):
    fecha_filter = ""
    params = [inversion, usuario]
    if fecha is not None:
        fecha_filter = " AND fecha <= ?"
        params.append(fecha)
    return conn.execute(
        f"""SELECT fecha, dinero_inicial, valor_actual, aplicacion, tipo_activo
            FROM inversiones
            WHERE inversion = ?
              AND usuario = ?
              {fecha_filter}
            ORDER BY fecha DESC, id DESC
            LIMIT 1""",
        tuple(params),
    ).fetchone()


def _capital_operaciones_hasta(conn, inversion, usuario, fecha=None, fallback_snapshot=True):
    fecha_filter = ""
    params = [inversion, usuario]
    if fecha is not None:
        fecha_filter = " AND fecha <= ?"
        params.append(fecha)
    rows = conn.execute(
        f"""SELECT id, tipo, importe, COALESCE(comisiones, 0)
            FROM operaciones_inversion
            WHERE inversion = ?
              AND usuario = ?
              {fecha_filter}
            ORDER BY fecha, id""",
        tuple(params),
    ).fetchall()
    if not rows and fallback_snapshot:
        snapshot = _latest_snapshot_activo(conn, inversion, usuario, fecha)
        return float(snapshot[1]) if snapshot else 0.0
    if not rows:
        return 0.0

    capital = 0.0
    for operacion_id, tipo, importe, comisiones in rows:
        importe = abs(float(importe or 0))
        comisiones = abs(float(comisiones or 0))
        if tipo == "Compra":
            capital += importe + comisiones
        elif tipo == "Venta":
            row_historico = conn.execute(
                """SELECT precio_compra
                   FROM historico_inversiones
                   WHERE operacion_id = ?
                     AND usuario = ?
                   LIMIT 1""",
                (operacion_id, usuario),
            ).fetchone()
            coste_vendido = float(row_historico[0] or 0) if row_historico else importe
            capital = max(0.0, capital - coste_vendido)
    return capital


def _tiene_operaciones_hasta(conn, inversion, usuario, fecha=None):
    fecha_filter = ""
    params = [inversion, usuario]
    if fecha is not None:
        fecha_filter = " AND fecha <= ?"
        params.append(fecha)
    return conn.execute(
        f"""SELECT COUNT(*)
            FROM operaciones_inversion
            WHERE inversion = ?
              AND usuario = ?
              {fecha_filter}""",
        tuple(params),
    ).fetchone()[0] > 0


def _recalcular_capital_snapshots_desde(conn, inversion, usuario, fecha_desde):
    rows = conn.execute(
        """SELECT id, fecha
           FROM inversiones
           WHERE inversion = ?
             AND usuario = ?
             AND fecha >= ?
           ORDER BY fecha, id""",
        (inversion, usuario, fecha_desde),
    ).fetchall()
    for snapshot_id, fecha_snapshot in rows:
        conn.execute(
            """UPDATE inversiones
               SET dinero_inicial = ?
               WHERE id = ?
                 AND usuario = ?""",
            (
                _capital_operaciones_hasta(
                    conn,
                    inversion,
                    usuario,
                    fecha_snapshot,
                    fallback_snapshot=False,
                ),
                snapshot_id,
                usuario,
            ),
        )


def _delete_orphan_asset(conn, inversion, usuario):
    conn.execute(
        """DELETE FROM activos
           WHERE inversion = ?
             AND usuario = ?
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
        (inversion, usuario),
    )


def _descripcion_operacion_inversion(tipo, inversion):
    return f"{tipo} inversion: {inversion}"


def _importe_liquidez_operacion(tipo, importe, comisiones):
    importe = abs(float(importe or 0))
    comisiones = abs(float(comisiones or 0))
    return -(importe + comisiones) if tipo == "Compra" else importe - comisiones


def _normalizar_unidades(valor):
    if valor in (None, "") or pd.isna(valor):
        raise ValueError("Indica el numero de acciones/participaciones.")
    unidades = abs(float(valor or 0))
    if unidades <= 0:
        raise ValueError("El numero de acciones/participaciones debe ser mayor que 0.")
    return unidades


def _precio_unitario_operacion(importe, unidades):
    if unidades in (None, 0):
        return None
    return abs(float(importe or 0)) / float(unidades)


def _validar_operacion_inversion(
    fecha,
    tipo,
    inversion,
    importe,
    cuenta,
    aplicacion,
    tipo_activo,
    comisiones,
    unidades=None,
):
    tipo = (tipo or "").strip()
    inversion = (inversion or "").strip()
    aplicacion = (aplicacion or "").strip()
    cuenta = aplicacion
    tipo_activo = (tipo_activo or "").strip() or "Sin clasificar"
    if tipo not in TIPOS_OPERACION_INVERSION:
        raise ValueError("Tipo de operacion de inversion no valido.")
    if not fecha or not inversion or not aplicacion:
        raise ValueError("Fecha, activo y broker son obligatorios.")
    importe = abs(float(importe or 0))
    comisiones = abs(float(comisiones or 0))
    if importe <= 0:
        raise ValueError("El importe debe ser mayor que 0.")
    if tipo == "Venta" and comisiones >= importe:
        raise ValueError("Las comisiones no pueden ser iguales o superiores al importe de venta.")
    unidades = _normalizar_unidades(unidades)
    precio_unitario = _precio_unitario_operacion(importe, unidades)
    return fecha, tipo, inversion, importe, cuenta, aplicacion, tipo_activo, comisiones, unidades, precio_unitario


def _unidades_operaciones_hasta(conn, inversion, usuario, fecha=None, exclude_operacion_id=None):
    params = [inversion, usuario]
    fecha_filter = ""
    if fecha is not None:
        fecha_filter = " AND fecha <= ?"
        params.append(fecha)
    exclude_filter = ""
    if exclude_operacion_id is not None:
        exclude_filter = " AND id != ?"
        params.append(exclude_operacion_id)
    row = conn.execute(
        f"""SELECT COALESCE(SUM(
                    CASE
                        WHEN tipo = 'Compra' THEN COALESCE(unidades, 0)
                        WHEN tipo = 'Venta' THEN -COALESCE(unidades, 0)
                        ELSE 0
                    END
                ), 0)
            FROM operaciones_inversion
            WHERE inversion = ?
              AND usuario = ?
              {fecha_filter}
              {exclude_filter}""",
        params,
    ).fetchone()
    return float(row[0] or 0)


def _validar_venta_unidades(conn, fecha, tipo, inversion, unidades, usuario, exclude_operacion_id=None):
    if tipo != "Venta" or unidades is None:
        return
    unidades_disponibles = _unidades_operaciones_hasta(
        conn, inversion, usuario, fecha, exclude_operacion_id
    )
    if unidades > unidades_disponibles + UNIDADES_EPSILON:
        raise ValueError(
            f"No se pueden vender {_formato_numero_es(unidades, 6, trim_zeros=True)} "
            f"acciones/participaciones de {inversion}: "
            f"hay {_formato_numero_es(unidades_disponibles, 6, trim_zeros=True)} disponibles."
        )


def _validar_unidades_requeridas_si_activo_las_usa(conn, inversion, usuario, unidades):
    if unidades is not None:
        return
    existe_unidades = conn.execute(
        """SELECT 1
           FROM operaciones_inversion
           WHERE inversion = ?
             AND usuario = ?
             AND unidades IS NOT NULL
           LIMIT 1""",
        (inversion, usuario),
    ).fetchone()
    if existe_unidades:
        raise ValueError(
            f"Indica el numero de acciones/participaciones de {inversion}. "
            "Este activo ya tiene operaciones con unidades registradas."
        )


def _validar_posicion_unidades_no_negativa(conn, inversion, usuario):
    operaciones = conn.execute(
        """SELECT fecha, id, tipo, unidades
           FROM operaciones_inversion
           WHERE inversion = ?
             AND usuario = ?
             AND unidades IS NOT NULL
           ORDER BY fecha, id""",
        (inversion, usuario),
    ).fetchall()
    posicion = 0.0
    for fecha, _, tipo, unidades in operaciones:
        unidades = float(unidades or 0)
        posicion += unidades if tipo == "Compra" else -unidades
        if posicion < -UNIDADES_EPSILON:
            raise ValueError(
                f"La posicion de {inversion} quedaria negativa el {fecha}. "
                "Revisa las unidades de compras y ventas."
            )


def _validar_venta_activo_registrado(conn, fecha, tipo, inversion, importe, usuario):
    if tipo != "Venta":
        return

    existe_activo = conn.execute(
        """SELECT 1
           FROM activos
           WHERE inversion = ?
             AND usuario = ?
           LIMIT 1""",
        (inversion, usuario),
    ).fetchone()
    if not existe_activo:
        raise ValueError("No se puede vender un activo no registrado.")

    snapshot = _latest_snapshot_activo(conn, inversion, usuario, fecha)
    if not snapshot:
        raise ValueError("No se puede vender un activo sin valoracion registrada.")

    ultimo_valor = float(snapshot[2] or 0)
    if importe > ultimo_valor:
        raise ValueError(
            f"No se puede vender {_formato_numero_es(importe, sufijo=' EUR')} de {inversion}: "
            f"su ultimo valor registrado es {_formato_numero_es(ultimo_valor, sufijo=' EUR')}."
        )


def _normalizar_cero_importe(valor):
    valor = float(valor or 0)
    return 0.0 if abs(valor) < IMPORTE_EPSILON else valor


def _upsert_posicion_abierta(
    conn,
    fecha,
    inversion,
    dinero_inicial,
    valor_actual,
    aplicacion,
    tipo_activo,
    usuario,
    operacion_id=None,
):
    cursor = conn.execute(
        """UPDATE inversiones
           SET dinero_inicial = ?,
               valor_actual = ?,
               aplicacion = ?,
               tipo_activo = ?,
               operacion_id = ?
           WHERE fecha = ?
             AND inversion = ?
             AND usuario = ?""",
        (dinero_inicial, valor_actual, aplicacion, tipo_activo, operacion_id, fecha, inversion, usuario),
    )
    if cursor.rowcount == 0:
        conn.execute(
            """INSERT INTO inversiones
               (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, operacion_id, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, operacion_id, usuario),
        )


def _registrar_venta_en_historico(conn, operacion_id, fecha, inversion, importe, comisiones, usuario):
    snapshot = _latest_snapshot_activo(conn, inversion, usuario, fecha)
    if not snapshot:
        raise ValueError("No se puede vender un activo sin valoracion registrada.")

    _, dinero_inicial, valor_actual, aplicacion, tipo_activo = snapshot
    dinero_inicial = float(dinero_inicial or 0)
    valor_actual = float(valor_actual or 0)
    if valor_actual <= 0:
        raise ValueError("No se puede vender un activo con valor actual 0.")
    if importe > valor_actual:
        raise ValueError(
            f"No se puede vender {_formato_numero_es(importe, sufijo=' EUR')} de {inversion}: "
            f"su ultimo valor registrado es {_formato_numero_es(valor_actual, sufijo=' EUR')}."
        )

    proporcion_vendida = min(1.0, importe / valor_actual)
    precio_compra = _normalizar_cero_importe(dinero_inicial * proporcion_vendida)
    valor_restante = _normalizar_cero_importe(valor_actual - importe)
    dinero_restante = _normalizar_cero_importe(dinero_inicial - precio_compra)
    comisiones = abs(float(comisiones or 0))
    aplicacion = aplicacion or ""
    tipo_activo = tipo_activo or "Sin clasificar"

    conn.execute(
        """INSERT INTO historico_inversiones
           (fecha, inversion, precio_compra, precio_venta, comisiones, aplicacion, tipo_activo, operacion_id, usuario)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(operacion_id, usuario) DO UPDATE SET
               fecha = excluded.fecha,
               inversion = excluded.inversion,
               precio_compra = excluded.precio_compra,
               precio_venta = excluded.precio_venta,
               comisiones = excluded.comisiones,
               aplicacion = excluded.aplicacion,
               tipo_activo = excluded.tipo_activo""",
        (fecha, inversion, precio_compra, importe, comisiones, aplicacion, tipo_activo, operacion_id, usuario),
    )
    _upsert_posicion_abierta(
        conn,
        fecha,
        inversion,
        dinero_restante,
        valor_restante,
        aplicacion,
        tipo_activo,
        usuario,
        operacion_id,
    )


def _restaurar_venta_historica(conn, operacion_id, usuario):
    row = conn.execute(
        """SELECT fecha, inversion, precio_compra, precio_venta, aplicacion, tipo_activo
           FROM historico_inversiones
           WHERE operacion_id = ?
             AND usuario = ?
           LIMIT 1""",
        (operacion_id, usuario),
    ).fetchone()
    if not row:
        return None

    fecha, inversion, precio_compra, precio_venta, aplicacion, tipo_activo = row
    snapshot = _latest_snapshot_activo(conn, inversion, usuario, fecha)
    dinero_base = float(snapshot[1] or 0) if snapshot else 0.0
    valor_base = float(snapshot[2] or 0) if snapshot else 0.0
    aplicacion = aplicacion or (snapshot[3] if snapshot else "") or ""
    tipo_activo = tipo_activo or (snapshot[4] if snapshot else "Sin clasificar") or "Sin clasificar"
    _upsert_posicion_abierta(
        conn,
        fecha,
        inversion,
        _normalizar_cero_importe(dinero_base + float(precio_compra or 0)),
        _normalizar_cero_importe(valor_base + float(precio_venta or 0)),
        aplicacion,
        tipo_activo,
        usuario,
    )
    conn.execute(
        """DELETE FROM historico_inversiones
           WHERE operacion_id = ?
             AND usuario = ?""",
        (operacion_id, usuario),
    )
    return fecha, inversion


def _ensure_catalogos_operacion(conn, cuenta, aplicacion, tipo_activo):
    conn.execute("INSERT OR IGNORE INTO cuentas (nombre) VALUES (?)", (cuenta,))
    conn.execute("INSERT OR IGNORE INTO sectores (nombre) VALUES (?)", ("Inversiones",))
    conn.execute("INSERT OR IGNORE INTO brokers (nombre) VALUES (?)", (aplicacion,))
    conn.execute("INSERT OR IGNORE INTO tipos_activo (nombre) VALUES (?)", (tipo_activo,))


def capital_invertido_activo(inversion, usuario, fecha=None):
    with conectar_db() as conn:
        return _capital_operaciones_hasta(conn, inversion, usuario, fecha)


def capitales_invertidos_por_activo(fecha, usuario):
    with conectar_db() as conn:
        activos = [
            row[0]
            for row in conn.execute(
                """SELECT inversion
                   FROM activos
                   WHERE usuario = ?
                   ORDER BY inversion COLLATE NOCASE""",
                (usuario,),
            ).fetchall()
        ]
        return {
            inversion: _capital_operaciones_hasta(conn, inversion, usuario, fecha)
            for inversion in activos
        }


def insertar_operacion_inversion(
    fecha,
    tipo,
    inversion,
    importe,
    cuenta,
    aplicacion,
    tipo_activo,
    usuario,
    unidades=None,
    precio_unitario=None,
    comisiones=0,
    notas="",
):
    (
        fecha,
        tipo,
        inversion,
        importe,
        cuenta,
        aplicacion,
        tipo_activo,
        comisiones,
        unidades,
        precio_unitario,
    ) = _validar_operacion_inversion(
        fecha, tipo, inversion, importe, cuenta, aplicacion, tipo_activo, comisiones, unidades
    )
    sector = "Inversiones"
    movimiento_liquidez = _importe_liquidez_operacion(tipo, importe, comisiones)
    tipo_transaccion = "Gasto" if movimiento_liquidez < 0 else "Ingreso"
    descripcion = _descripcion_operacion_inversion(tipo, inversion)
    fecha_registro = _fecha_registro_actual()

    with conectar_db() as conn:
        _validar_venta_activo_registrado(conn, fecha, tipo, inversion, importe, usuario)
        _validar_unidades_requeridas_si_activo_las_usa(conn, inversion, usuario, unidades)
        _validar_venta_unidades(conn, fecha, tipo, inversion, unidades, usuario)
        _ensure_catalogos_operacion(conn, cuenta, aplicacion, tipo_activo)
        conn.execute(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            (inversion, aplicacion, tipo_activo, usuario),
        )
        tx_cursor = conn.execute(
            """INSERT INTO transacciones
               (fecha, fecha_registro, tipo, descripcion, cuenta, sector, importe, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fecha,
                fecha_registro,
                tipo_transaccion,
                descripcion,
                cuenta,
                sector,
                movimiento_liquidez,
                usuario,
            ),
        )
        transaccion_id = tx_cursor.lastrowid
        op_cursor = conn.execute(
            """INSERT INTO operaciones_inversion
               (fecha, fecha_registro, inversion, tipo, importe, unidades, precio_unitario,
                comisiones, cuenta, transaccion_id, notas, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fecha,
                fecha_registro,
                inversion,
                tipo,
                importe,
                unidades,
                precio_unitario,
                comisiones,
                cuenta,
                transaccion_id,
                notas or "",
                usuario,
            ),
        )
        operacion_id = op_cursor.lastrowid
        if tipo == "Venta":
            _registrar_venta_en_historico(conn, operacion_id, fecha, inversion, importe, comisiones, usuario)

        _validar_posicion_unidades_no_negativa(conn, inversion, usuario)
        _recalcular_capital_snapshots_desde(conn, inversion, usuario, fecha)
        conn.commit()
    return transaccion_id


def actualizar_operacion_inversion(
    operacion_id,
    fecha,
    tipo,
    inversion,
    importe,
    cuenta,
    aplicacion,
    tipo_activo,
    usuario,
    comisiones=0,
    unidades=None,
):
    (
        fecha,
        tipo,
        inversion,
        importe,
        cuenta,
        aplicacion,
        tipo_activo,
        comisiones,
        unidades,
        precio_unitario,
    ) = _validar_operacion_inversion(
        fecha, tipo, inversion, importe, cuenta, aplicacion, tipo_activo, comisiones, unidades
    )
    with conectar_db() as conn:
        operacion = conn.execute(
            """SELECT fecha, inversion, tipo, transaccion_id
               FROM operaciones_inversion
               WHERE id = ?
                 AND usuario = ?""",
            (operacion_id, usuario),
        ).fetchone()
        if not operacion:
            raise ValueError("La operacion de inversion no existe.")
        fecha_anterior, inversion_anterior, tipo_anterior, transaccion_id = operacion
        restaurada = _restaurar_venta_historica(conn, operacion_id, usuario) if tipo_anterior == "Venta" else None
        _validar_venta_activo_registrado(conn, fecha, tipo, inversion, importe, usuario)
        _validar_unidades_requeridas_si_activo_las_usa(conn, inversion, usuario, unidades)
        _validar_venta_unidades(conn, fecha, tipo, inversion, unidades, usuario, operacion_id)
        _ensure_catalogos_operacion(conn, cuenta, aplicacion, tipo_activo)
        conn.execute(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            (inversion, aplicacion, tipo_activo, usuario),
        )
        conn.execute(
            """UPDATE operaciones_inversion
               SET fecha = ?,
                   inversion = ?,
                   tipo = ?,
                   importe = ?,
                   unidades = ?,
                   precio_unitario = ?,
                   comisiones = ?,
                   cuenta = ?,
                   notas = ''
               WHERE id = ?
                 AND usuario = ?""",
            (fecha, inversion, tipo, importe, unidades, precio_unitario, comisiones, cuenta, operacion_id, usuario),
        )
        movimiento_liquidez = _importe_liquidez_operacion(tipo, importe, comisiones)
        conn.execute(
            """UPDATE transacciones
               SET fecha = ?,
                   tipo = ?,
                   descripcion = ?,
                   cuenta = ?,
                   sector = ?,
                   importe = ?
               WHERE id = ?
                 AND usuario = ?""",
            (
                fecha,
                "Gasto" if movimiento_liquidez < 0 else "Ingreso",
                _descripcion_operacion_inversion(tipo, inversion),
                cuenta,
                "Inversiones",
                movimiento_liquidez,
                transaccion_id,
                usuario,
            ),
        )
        if tipo == "Venta":
            _registrar_venta_en_historico(conn, operacion_id, fecha, inversion, importe, comisiones, usuario)
        fecha_recalculo = min(str(fecha_anterior), str(fecha))
        if restaurada is not None:
            fecha_recalculo = min(fecha_recalculo, str(restaurada[0]))
        if inversion_anterior != inversion:
            _recalcular_capital_snapshots_desde(conn, inversion_anterior, usuario, str(fecha_anterior))
            _validar_posicion_unidades_no_negativa(conn, inversion_anterior, usuario)
            _delete_orphan_asset(conn, inversion_anterior, usuario)
        elif restaurada is not None and restaurada[1] != inversion:
            _recalcular_capital_snapshots_desde(conn, restaurada[1], usuario, str(restaurada[0]))
            _validar_posicion_unidades_no_negativa(conn, restaurada[1], usuario)
            _delete_orphan_asset(conn, restaurada[1], usuario)
        _validar_posicion_unidades_no_negativa(conn, inversion, usuario)
        _recalcular_capital_snapshots_desde(conn, inversion, usuario, fecha_recalculo)
        conn.commit()


def eliminar_operacion_inversion(operacion_id, usuario):
    with conectar_db() as conn:
        operacion = conn.execute(
            """SELECT fecha, inversion, tipo, transaccion_id
               FROM operaciones_inversion
               WHERE id = ?
                 AND usuario = ?""",
            (operacion_id, usuario),
        ).fetchone()
        if not operacion:
            raise ValueError("La operacion de inversion no existe.")
        fecha, inversion, tipo, transaccion_id = operacion
        if tipo == "Venta":
            _restaurar_venta_historica(conn, operacion_id, usuario)
        conn.execute(
            "DELETE FROM operaciones_inversion WHERE id = ? AND usuario = ?",
            (operacion_id, usuario),
        )
        if transaccion_id:
            conn.execute(
                "DELETE FROM transacciones WHERE id = ? AND usuario = ?",
                (transaccion_id, usuario),
            )
        _recalcular_capital_snapshots_desde(conn, inversion, usuario, fecha)
        _delete_orphan_asset(conn, inversion, usuario)
        conn.commit()


def insertar_inversion(fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario):
    with conectar_db() as conn:
        conn.execute(
            """INSERT INTO inversiones
               (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario),
        )
        conn.execute(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            (inversion, aplicacion, tipo_activo, usuario),
        )
        conn.commit()


def insertar_inversiones(registros, usuario):
    registros_usuario = [(*registro, usuario) for registro in registros]
    with conectar_db() as conn:
        conn.executemany(
            """INSERT INTO inversiones
               (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            registros_usuario,
        )
        conn.executemany(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            [(registro[1], registro[4], registro[5], usuario) for registro in registros],
        )
        conn.commit()


def registros_inversion_existentes(registros, usuario):
    existentes = []
    with conectar_db() as conn:
        for fecha, inversion, _, _, aplicacion, _ in registros:
            row = conn.execute(
                """SELECT id, fecha, inversion, aplicacion
                   FROM inversiones
                   WHERE fecha = ?
                     AND inversion = ?
                     AND usuario = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (fecha, inversion, usuario),
            ).fetchone()
            if row:
                existentes.append({
                    "id": row[0],
                    "fecha": row[1],
                    "inversion": row[2],
                    "aplicacion": row[3],
                })
    return existentes


def upsert_inversiones_por_fecha_activo(registros, usuario):
    with conectar_db() as conn:
        for fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo in registros:
            if _tiene_operaciones_hasta(conn, inversion, usuario, fecha):
                dinero_inicial = _capital_operaciones_hasta(conn, inversion, usuario, fecha)
            cursor = conn.execute(
                """UPDATE inversiones
                   SET dinero_inicial = ?,
                       valor_actual = ?,
                       aplicacion = ?,
                       tipo_activo = ?
                   WHERE fecha = ?
                     AND inversion = ?
                     AND usuario = ?""",
                (dinero_inicial, valor_actual, aplicacion, tipo_activo, fecha, inversion, usuario),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    """INSERT INTO inversiones
                       (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fecha, inversion, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario),
                )
            conn.execute(
                """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(inversion, usuario) DO UPDATE SET
                       aplicacion = excluded.aplicacion,
                       tipo_activo = excluded.tipo_activo""",
                (inversion, aplicacion, tipo_activo, usuario),
            )
        conn.commit()


def actualizar_registro_inversion(inversion_id, fecha, dinero_inicial, valor_actual, aplicacion, tipo_activo, usuario):
    with conectar_db() as conn:
        row = conn.execute(
            "SELECT inversion FROM inversiones WHERE id = ? AND usuario = ?",
            (inversion_id, usuario),
        ).fetchone()
        if not row:
            raise ValueError("El registro de inversion no existe.")
        inversion = row[0]
        if _tiene_operaciones_hasta(conn, inversion, usuario, fecha):
            dinero_inicial = _capital_operaciones_hasta(conn, inversion, usuario, fecha)
        conn.execute(
            """UPDATE inversiones
               SET fecha = ?,
                   dinero_inicial = ?,
                   valor_actual = ?,
                   aplicacion = ?,
                   tipo_activo = ?
               WHERE id = ?
                 AND usuario = ?""",
            (fecha, dinero_inicial, valor_actual, aplicacion, tipo_activo, inversion_id, usuario),
        )
        conn.execute(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            (inversion, aplicacion, tipo_activo, usuario),
        )
        conn.commit()


def actualizar_clasificacion_inversiones(registros, usuario):
    with conectar_db() as conn:
        for aplicacion, tipo_activo, inversion in registros:
            conn.execute(
                """UPDATE inversiones
                   SET aplicacion = ?, tipo_activo = ?
                   WHERE inversion = ? AND usuario = ?""",
                (aplicacion, tipo_activo, inversion, usuario),
            )
            conn.execute(
                """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(inversion, usuario) DO UPDATE SET
                       aplicacion = excluded.aplicacion,
                       tipo_activo = excluded.tipo_activo""",
                (inversion, aplicacion, tipo_activo, usuario),
            )
        conn.commit()


def cargar_cotizaciones_activos(usuario):
    with conectar_db() as conn:
        rows = conn.execute(
            """SELECT inversion, ticker_yahoo, divisa_cotizacion, divisa_valoracion,
                      auto_update_enabled, logo_url
               FROM activos_cotizacion
               WHERE usuario = ?""",
            (usuario,),
        ).fetchall()
    return {
        row[0]: {
            "ticker_yahoo": row[1] or "",
            "divisa_cotizacion": row[2] or "",
            "divisa_valoracion": row[3] or "EUR",
            "auto_update_enabled": bool(row[4] if row[4] is not None else 1),
            "logo_url": row[5] or "",
        }
        for row in rows
    }


def guardar_cotizaciones_activos(registros, usuario):
    with conectar_db() as conn:
        for registro in registros:
            inversion = (registro.get("inversion") or "").strip()
            ticker = (registro.get("ticker_yahoo") or "").strip().upper()
            if not inversion:
                continue
            divisa_cotizacion = (registro.get("divisa_cotizacion") or "").strip().upper()
            divisa_valoracion = (registro.get("divisa_valoracion") or "EUR").strip().upper() or "EUR"
            logo_url = (registro.get("logo_url") or "").strip()
            if not ticker and not divisa_cotizacion and not logo_url:
                conn.execute(
                    """DELETE FROM activos_cotizacion
                       WHERE usuario = ? AND inversion = ?""",
                    (usuario, inversion),
                )
                continue
            auto_update_enabled = 1 if ticker and registro.get("auto_update_enabled", True) else 0
            conn.execute(
                """INSERT INTO activos_cotizacion
                   (usuario, inversion, ticker_yahoo, divisa_cotizacion, divisa_valoracion,
                    auto_update_enabled, logo_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(usuario, inversion) DO UPDATE SET
                       ticker_yahoo = excluded.ticker_yahoo,
                       divisa_cotizacion = excluded.divisa_cotizacion,
                       divisa_valoracion = excluded.divisa_valoracion,
                       auto_update_enabled = excluded.auto_update_enabled,
                       logo_url = COALESCE(NULLIF(excluded.logo_url, ''), activos_cotizacion.logo_url)""",
                (
                    usuario,
                    inversion,
                    ticker,
                    divisa_cotizacion,
                    divisa_valoracion,
                    auto_update_enabled,
                    logo_url,
                ),
            )
        conn.commit()


def actualizar_logo_activo(inversion, logo_url, usuario):
    inversion = (inversion or "").strip()
    logo_url = (logo_url or "").strip()
    if not inversion:
        return
    with conectar_db() as conn:
        conn.execute(
            """INSERT INTO activos_cotizacion
               (usuario, inversion, ticker_yahoo, divisa_cotizacion, divisa_valoracion,
                auto_update_enabled, logo_url)
               VALUES (?, ?, '', '', 'EUR', 0, ?)
               ON CONFLICT(usuario, inversion) DO UPDATE SET
                   logo_url = excluded.logo_url""",
            (usuario, inversion, logo_url),
        )
        conn.commit()


def existe_nombre_activo(inversion, usuario):
    with conectar_db() as conn:
        return conn.execute(
            """SELECT COUNT(*)
               FROM activos
               WHERE inversion = ?
                 AND usuario = ?""",
            (inversion, usuario),
        ).fetchone()[0] > 0


def actualizar_clasificacion_inversiones_legacy(registros, usuario):
    with conectar_db() as conn:
        conn.executemany(
            """UPDATE inversiones
               SET aplicacion = ?, tipo_activo = ?
               WHERE inversion = ? AND usuario = ?""",
            [(*registro, usuario) for registro in registros],
        )
        conn.executemany(
            """INSERT INTO activos (inversion, aplicacion, tipo_activo, usuario)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(inversion, usuario) DO UPDATE SET
                   aplicacion = excluded.aplicacion,
                   tipo_activo = excluded.tipo_activo""",
            [(inversion, aplicacion, tipo_activo, usuario) for aplicacion, tipo_activo, inversion in registros],
        )
        conn.commit()


def cargar_catalogo(tabla):
    if tabla not in CATALOGOS_PERMITIDOS:
        raise ValueError("Catálogo no válido")
    with conectar_db() as conn:
        return [
            fila[0]
            for fila in conn.execute(f"SELECT nombre FROM {tabla} ORDER BY nombre COLLATE NOCASE")
        ]


def insertar_catalogo(tabla, nombre):
    if tabla not in CATALOGOS_PERMITIDOS:
        raise ValueError("Catálogo no válido")
    ejecutar_query(f"INSERT INTO {tabla} (nombre) VALUES (?)", (nombre,))


def reemplazar_catalogo(tabla, nombres):
    if tabla not in {"brokers", "cuentas", "sectores"}:
        raise ValueError("Catálogo no válido")
    nombres_limpios = []
    vistos = set()
    for nombre in nombres:
        nombre = (nombre or "").strip()
        clave = nombre.lower()
        if nombre and clave not in vistos:
            nombres_limpios.append(nombre)
            vistos.add(clave)
    with conectar_db() as conn:
        conn.execute(f"DELETE FROM {tabla}")
        conn.executemany(
            f"INSERT INTO {tabla} (nombre) VALUES (?)",
            [(nombre,) for nombre in nombres_limpios],
        )
        conn.commit()


def configurar_catalogos_iniciales(cuentas, sectores, brokers):
    reemplazar_catalogo("cuentas", cuentas)
    reemplazar_catalogo("sectores", sectores)
    reemplazar_catalogo("brokers", brokers)


def eliminar_catalogo(tabla, nombre, usuario=None):
    if tabla == "cuentas":
        usuario_filter = ""
        params = [nombre, nombre]
        if usuario is not None:
            usuario_filter = " AND usuario = ?"
            params.append(usuario)
        params.append(nombre)
        if usuario is not None:
            params.append(usuario)
        with conectar_db() as conn:
            cursor = conn.execute(
                f"""DELETE FROM cuentas
                    WHERE nombre = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM transacciones
                          WHERE cuenta = ?{usuario_filter}
                      )
                      AND NOT EXISTS (
                          SELECT 1
                          FROM brokers
                          WHERE brokers.nombre = ?
                            AND EXISTS (
                                SELECT 1
                                FROM inversiones
                                WHERE inversiones.aplicacion = brokers.nombre{usuario_filter}
                            )
                      )""",
                tuple(params),
            )
            conn.commit()
            return cursor.rowcount > 0

    configuracion = {
        "brokers": ("inversiones", "aplicacion"),
        "tipos_activo": ("inversiones", "tipo_activo"),
        "sectores": ("transacciones", "sector"),
    }
    if tabla not in configuracion:
        raise ValueError("Catálogo no válido")
    tabla_uso, columna = configuracion[tabla]
    usuario_filter = ""
    params = [nombre, nombre]
    if usuario is not None and tabla_uso in TABLAS_CON_USUARIO:
        usuario_filter = " AND usuario = ?"
        params.append(usuario)
    with conectar_db() as conn:
        cursor = conn.execute(
            f"""DELETE FROM {tabla}
                WHERE nombre = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM {tabla_uso}
                      WHERE {columna} = ?{usuario_filter}
                  )""",
            tuple(params),
        )
        conn.commit()
        return cursor.rowcount > 0


def usos_catalogo(columna, usuario=None):
    configuracion = {
        "aplicacion": ("inversiones", "inversion"),
        "tipo_activo": ("inversiones", "inversion"),
        "cuenta": ("transacciones", "id"),
        "sector": ("transacciones", "id"),
    }
    if columna not in configuracion:
        raise ValueError("Columna de catálogo no válida")
    tabla, campo_conteo = configuracion[columna]
    usuario_filter = ""
    params = ()
    if usuario is not None and tabla in TABLAS_CON_USUARIO:
        usuario_filter = " AND usuario = ?"
        params = (usuario,)
    with conectar_db() as conn:
        usos = dict(
            conn.execute(
                f"""SELECT {columna}, COUNT(DISTINCT {campo_conteo})
                    FROM {tabla}
                    WHERE {columna} IS NOT NULL
                      AND TRIM({columna}) != ''
                      {usuario_filter}
                    GROUP BY {columna}""",
                params,
            ).fetchall()
        )
        if columna == "cuenta":
            broker_params = ()
            broker_usuario_filter = ""
            if usuario is not None:
                broker_usuario_filter = " AND usuario = ?"
                broker_params = (usuario,)
            for cuenta, cantidad in conn.execute(
                f"""SELECT aplicacion, COUNT(DISTINCT id)
                    FROM inversiones
                    WHERE aplicacion IS NOT NULL
                      AND TRIM(aplicacion) != ''
                      {broker_usuario_filter}
                    GROUP BY aplicacion""",
                broker_params,
            ).fetchall():
                usos[cuenta] = usos.get(cuenta, 0) + cantidad
        return usos


def eliminar_inversion(inversion_id, usuario):
    with conectar_db() as conn:
        row = conn.execute(
            "SELECT inversion, operacion_id FROM inversiones WHERE id = ? AND usuario = ?",
            (inversion_id, usuario),
        ).fetchone()
        if not row:
            return
        inversion, operacion_id = row
        if operacion_id is not None:
            raise ValueError(
                "No se puede eliminar un registro de valoracion generado automaticamente por una venta."
            )
        conn.execute("DELETE FROM inversiones WHERE id = ? AND usuario = ?", (inversion_id, usuario))
        conn.execute(
            """DELETE FROM activos
               WHERE inversion = ?
                 AND usuario = ?
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
            (inversion, usuario),
        )
        conn.commit()
