from datetime import date, timedelta

import pandas as pd


ASSET_KEY_COLUMNS = ["inversion"]


def opciones_con_historial(df, columna, opciones_base, opcion_otro):
    opciones = list(opciones_base)
    if not df.empty and columna in df:
        for valor in df[columna].dropna().astype(str).str.strip():
            if valor and valor not in opciones and valor != opcion_otro:
                opciones.append(valor)
    opciones.append(opcion_otro)
    return opciones


def opciones_por_uso_reciente(df, columna, opciones_base, opcion_otro, dias=60, hoy=None):
    opciones = []
    vistos = set()
    for opcion in opciones_base:
        opcion = (opcion or "").strip()
        clave = opcion.lower()
        if opcion and clave not in vistos and opcion != opcion_otro:
            opciones.append(opcion)
            vistos.add(clave)

    if df.empty or columna not in df:
        return [*opciones, opcion_otro]

    df_hist = df.copy()
    for valor in df_hist[columna].dropna().astype(str).str.strip():
        clave = valor.lower()
        if valor and clave not in vistos and valor != opcion_otro:
            opciones.append(valor)
            vistos.add(clave)

    hoy = hoy or date.today()
    fecha_minima = hoy - timedelta(days=dias)
    recientes = df_hist.copy()
    recientes["fecha"] = pd.to_datetime(recientes["fecha"], errors="coerce").dt.date
    recientes = recientes[recientes["fecha"] >= fecha_minima]
    counts = {}
    if not recientes.empty:
        counts = recientes[columna].dropna().astype(str).str.strip().value_counts().to_dict()

    opciones = sorted(opciones, key=lambda nombre: (-counts.get(nombre, 0), nombre.lower()))
    opciones.append(opcion_otro)
    return opciones


def ultimo_traspaso_entre_cuentas(df_tx):
    if df_tx.empty:
        return None, None
    df = df_tx.copy()
    df = df[df["tipo"] == "Traspaso"].copy()
    if df.empty:
        return None, None
    df["fecha_orden"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.sort_values(["fecha_orden", "id"], ascending=[False, False])
    salidas = df[df["importe"] < 0]
    for _, salida in salidas.iterrows():
        descripcion = str(salida["descripcion"] or "")
        base = descripcion.removesuffix(" - salida")
        entradas = df[
            (df["fecha"] == salida["fecha"])
            & (df["importe"] > 0)
            & (df["descripcion"].astype(str).isin([f"{base} - entrada", base]))
        ]
        if not entradas.empty:
            return salida["cuenta"], entradas.iloc[0]["cuenta"]

    fecha_ultima = df.iloc[0]["fecha"]
    mismo_dia = df[df["fecha"] == fecha_ultima]
    origen = mismo_dia[mismo_dia["importe"] < 0]
    destino = mismo_dia[mismo_dia["importe"] > 0]
    return (
        origen.iloc[0]["cuenta"] if not origen.empty else None,
        destino.iloc[0]["cuenta"] if not destino.empty else None,
    )


def primer_dia_mes_anterior(hoy=None):
    hoy = hoy or date.today()
    primer_dia_mes_actual = date(hoy.year, hoy.month, 1)
    ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
    return date(ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month, 1)


def normalizar_sector(valor):
    valor = "" if pd.isna(valor) else str(valor).strip()
    return valor or "Sin sector"


def resumen_gasto_por_sector(df_tx, fecha_inicio, fecha_fin=None, sectores=None):
    if df_tx.empty:
        return pd.DataFrame(columns=["Sector", "Gastos", "Ingresos", "Balance"])
    df = df_tx.copy()
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df = df[df["fecha"] >= fecha_inicio]
    if fecha_fin is not None:
        df = df[df["fecha"] <= fecha_fin]
    if df.empty:
        return pd.DataFrame(columns=["Sector", "Gastos", "Ingresos", "Balance"])
    df["sector"] = df["sector"].apply(normalizar_sector)
    if sectores is not None:
        df = df[df["sector"].isin(sectores)]
    if df.empty:
        return pd.DataFrame(columns=["Sector", "Gastos", "Ingresos", "Balance"])
    resumen = df.groupby("sector")["importe"].agg(
        Gastos=lambda valores: abs(valores[valores < 0].sum()),
        Ingresos=lambda valores: valores[valores > 0].sum(),
        Balance="sum",
    ).reset_index()
    return resumen.rename(columns={"sector": "Sector"}).sort_values(["Gastos", "Sector"], ascending=[False, True])


def filtrar_transacciones(df_tx, fecha_inicio, sector=None, fecha_fin=None):
    if df_tx.empty:
        return df_tx.copy()
    df = df_tx.copy()
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["sector"] = df["sector"].apply(normalizar_sector)
    df = df[df["fecha"] >= fecha_inicio]
    if fecha_fin is not None:
        df = df[df["fecha"] <= fecha_fin]
    if sector is not None:
        df = df[df["sector"] == sector]
    return df.sort_values(["fecha", "id"], ascending=[False, False])


def calcular_liquidez_por_fecha(df_tx):
    if df_tx.empty:
        return pd.DataFrame(columns=["Fecha", "Liquidez"])
    liquidez = df_tx.copy()
    liquidez["Fecha"] = pd.to_datetime(liquidez["fecha"])
    liquidez = liquidez.groupby("Fecha", as_index=False)["importe"].sum().sort_values("Fecha")
    liquidez["Liquidez"] = liquidez["importe"].cumsum()
    liquidez["Fecha"] = liquidez["Fecha"].dt.strftime("%Y-%m-%d")
    return liquidez[["Fecha", "Liquidez"]]


def calcular_patrimonio_total_por_fecha(df_tx, df_inv):
    fechas = []
    if not df_tx.empty:
        fechas.extend(pd.to_datetime(df_tx["fecha"]).tolist())
    if not df_inv.empty:
        fechas.extend(pd.to_datetime(df_inv["fecha"]).tolist())
    if not fechas:
        return pd.DataFrame(columns=["Fecha", "Liquidez", "Valor inversiones", "Patrimonio total"])

    fechas = sorted(pd.Series(fechas).dt.normalize().drop_duplicates())
    tx = df_tx.copy()
    inv = df_inv.copy()
    if not tx.empty:
        tx["fecha"] = pd.to_datetime(tx["fecha"]).dt.normalize()
    if not inv.empty:
        inv["fecha"] = pd.to_datetime(inv["fecha"]).dt.normalize()

    filas = []
    for fecha in fechas:
        liquidez = tx[tx["fecha"] <= fecha]["importe"].sum() if not tx.empty else 0.0
        valor_inversiones = 0.0
        if not inv.empty:
            snapshots = inv[inv["fecha"] <= fecha]
            if not snapshots.empty:
                ultimos = snapshots.sort_values(["fecha", "id"]).drop_duplicates(ASSET_KEY_COLUMNS, keep="last")
                valor_inversiones = ultimos["valor_actual"].sum()
        filas.append({
            "Fecha": fecha.strftime("%Y-%m-%d"),
            "Liquidez": liquidez,
            "Valor inversiones": valor_inversiones,
            "Patrimonio total": liquidez + valor_inversiones,
        })
    return pd.DataFrame(filas)


def calcular_evolucion_inversiones(df_inv):
    if df_inv.empty:
        return pd.DataFrame(columns=["Fecha", "Capital invertido", "Valor actual", "Diferencia (%)"])
    df = df_inv.copy()
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.normalize()
    df = df.sort_values(["inversion", "fecha", "id"])
    fechas = sorted(df["fecha"].drop_duplicates())
    filas = []
    for fecha in fechas:
        snapshots = df[df["fecha"] <= fecha]
        if snapshots.empty:
            continue
        ultimos = snapshots.sort_values(["fecha", "id"]).drop_duplicates(ASSET_KEY_COLUMNS, keep="last")
        capital = ultimos["dinero_inicial"].sum()
        valor = ultimos["valor_actual"].sum()
        diferencia = ((valor - capital) / capital * 100) if capital else 0.0
        filas.append({
            "Fecha": fecha.strftime("%Y-%m-%d"),
            "Capital invertido": capital,
            "Valor actual": valor,
            "Diferencia (%)": diferencia,
        })
    return pd.DataFrame(filas)


def calcular_distribucion_inversiones_por_tipo(df_inv):
    if df_inv.empty:
        return pd.DataFrame(columns=["Tipo de activo", "Valor actual"])

    df = df_inv.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    ultima_fecha = df["fecha"].max()
    if pd.isna(ultima_fecha):
        return pd.DataFrame(columns=["Tipo de activo", "Valor actual"])

    ultimos = df.sort_values(["fecha", "id"]).drop_duplicates(ASSET_KEY_COLUMNS, keep="last").copy()
    if "tipo_activo" not in ultimos:
        ultimos["tipo_activo"] = "Sin clasificar"
    ultimos["tipo_activo"] = ultimos["tipo_activo"].fillna("Sin clasificar").replace("", "Sin clasificar")

    distribucion = (
        ultimos.groupby("tipo_activo", as_index=False)["valor_actual"]
        .sum()
        .rename(columns={"tipo_activo": "Tipo de activo", "valor_actual": "Valor actual"})
    )
    return distribucion[distribucion["Valor actual"] > 0].sort_values("Valor actual", ascending=False)
