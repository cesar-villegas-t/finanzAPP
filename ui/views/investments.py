from datetime import date
import sqlite3
from urllib.parse import quote_plus

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import run, ui

from db.queries import (
    actualizar_clasificacion_inversiones,
    actualizar_operacion_inversion,
    actualizar_registro_inversion,
    capitales_invertidos_por_activo,
    cargar_cotizaciones_activos,
    cargar_catalogo,
    cargar_datos,
    eliminar_catalogo,
    eliminar_inversion,
    eliminar_operacion_inversion,
    existe_nombre_activo,
    insertar_operacion_inversion,
    insertar_catalogo,
    guardar_cotizaciones_activos,
    registros_inversion_existentes,
    upsert_inversiones_por_fecha_activo,
    usos_catalogo,
)
from services.analytics import (
    calcular_distribucion_inversiones_por_tipo,
    calcular_evolucion_inversiones,
)
from services.asset_logos import obtener_logo_activo, sincronizar_logo_activo, url_avatar_fallback
from services.market_prices import buscar_info_ticker_yahoo, obtener_valor_mercado
from ui.components import (
    color_por_signo,
    formato_euros,
    formato_euros_sin_signo,
    formato_numero,
    formato_porcentaje,
    formato_unidades,
    refresh_view,
)


COLOR_PRIMARY = "#2563EB"
COLOR_POSITIVE = "#10B981"
COLOR_NEGATIVE = "#F43F5E"
COLOR_TEXT_MUTED = "#64748B"
COLOR_GRID_SUBTLE = "#F1F5F9"
CHART_COLORS = ["#3B82F6", "#06B6D4", "#8B5CF6", "#F97316", "#F43F5E"]
LINE_TYPE = "spline" # Options: "linear", "spline"


def prepare_chart(fig, height=520):
    fig.update_layout(
        autosize=True,
        height=height,
        margin={"l": 24, "r": 24, "t": 48, "b": 24},
        separators=",.",
    )
    return fig


def formato_euros_hover(valor):
    return formato_numero(valor, sufijo=" €")


def rgba_from_hex(color, opacity):
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {opacity})"


def url_catalog_avatar(nombre, size=128):
    nombre = quote_plus(str(nombre or "Activo"))
    return (
        "https://ui-avatars.com/api/"
        f"?name={nombre}&background=EFF6FF&color=2563EB&bold=true&size={size}"
    )


def build_investment_evolution_chart(evolucion):
    chart_data = evolucion.copy()
    chart_data["Fecha"] = pd.to_datetime(chart_data["Fecha"])
    chart_data["Fecha hover"] = chart_data["Fecha"].dt.strftime("%d/%m/%Y")
    chart_data["Valor inicial hover"] = chart_data["Capital invertido"].apply(
        formato_euros_hover
    )
    chart_data["Valor actual hover"] = chart_data["Valor actual"].apply(
        formato_euros_hover
    )
    chart_data["Rentabilidad hover"] = chart_data["Diferencia (%)"].apply(
        lambda valor: (
            f"<span style='color:{COLOR_POSITIVE if valor >= 0 else COLOR_NEGATIVE}'>"
            f"{formato_porcentaje(valor, signed=True)}</span>"
        )
    )
    hover_data = chart_data[
        ["Fecha hover", "Valor inicial hover", "Valor actual hover", "Rentabilidad hover"]
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["Fecha"],
            y=chart_data["Capital invertido"],
            customdata=hover_data,
            mode="lines",
            name="Valor inicial",
            line={"color": COLOR_PRIMARY, "width": 3, "shape": LINE_TYPE, "smoothing": 0.4},
            marker={"color": COLOR_PRIMARY, "size": 8},
            fill="tozeroy",
            fillgradient={
                "type": "vertical",
                "colorscale": [
                    [0, rgba_from_hex(COLOR_PRIMARY, 0.02)],
                    [1, rgba_from_hex(COLOR_PRIMARY, 0.16)],
                ],
            },
            hovertemplate=(
                "%{customdata[0]}<br>"
                "Valor inicial: %{customdata[1]}<br>"
                "Valor actual: %{customdata[2]}<br>"
                "Ganancia/pérdida: %{customdata[3]}"
                "<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_data["Fecha"],
            y=chart_data["Valor actual"],
            customdata=hover_data,
            mode="lines",
            name="Valor actual",
            line={"color": COLOR_POSITIVE, "width": 3, "shape": LINE_TYPE, "smoothing": 0.4},
            marker={"color": COLOR_POSITIVE, "size": 8},
            fill="tozeroy",
            fillgradient={
                "type": "vertical",
                "colorscale": [
                    [0, rgba_from_hex(COLOR_POSITIVE, 0.02)],
                    [1, rgba_from_hex(COLOR_POSITIVE, 0.24)],
                ],
            },
            hovertemplate=(
                "%{customdata[0]}<br>"
                "Valor inicial: %{customdata[1]}<br>"
                "Valor actual: %{customdata[2]}<br>"
                "Ganancia/pérdida: %{customdata[3]}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="rgba(255,255,255,0)",
        legend_title_text="",
        separators=",.",
        hovermode="closest",
        hoverlabel={
            "align": "left",
            "bgcolor": "#FFFFFF",
            "bordercolor": COLOR_GRID_SUBTLE,
            "font": {"color": "#1E293B", "size": 13},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=COLOR_GRID_SUBTLE,
        zeroline=False,
        ticksuffix="\u20ac",
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    return fig


def preparar_evolucion_activo_chart(evolucion, df_asset_ops, clave_activo):
    chart_data = evolucion.copy()
    chart_data["Fecha plot"] = pd.to_datetime(chart_data["Fecha"], errors="coerce")
    chart_data["Fecha hover"] = chart_data["Fecha plot"].dt.strftime("%d/%m/%Y")
    chart_data["Valor posición"] = pd.to_numeric(chart_data["Valor actual"], errors="coerce").fillna(0.0)
    chart_data["Participaciones totales"] = chart_data["Fecha"].apply(
        lambda fecha: unidades_actuales_por_activo(df_asset_ops, fecha).get(clave_activo)
    )
    chart_data["Precio unitario"] = chart_data.apply(
        lambda row: (
            row["Valor posición"] / row["Participaciones totales"]
            if row["Participaciones totales"] and row["Participaciones totales"] > 0
            else None
        ),
        axis=1,
    )
    chart_data["Valor posición hover"] = chart_data["Valor posición"].apply(formato_euros_hover)
    chart_data["Participaciones hover"] = chart_data["Participaciones totales"].apply(formato_unidades)
    chart_data["Precio unitario hover"] = chart_data["Precio unitario"].apply(
        lambda valor: formato_euros_hover(float(valor)) if valor is not None and not pd.isna(valor) else "-"
    )
    return chart_data


def aplicar_estilo_chart_activo(fig, ticksuffix="\u20ac"):
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        separators=",.",
        showlegend=False,
        hovermode="closest",
        hoverlabel={
            "align": "left",
            "bgcolor": "#FFFFFF",
            "bordercolor": COLOR_GRID_SUBTLE,
            "font": {"color": "#1E293B", "size": 13},
        },
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=COLOR_GRID_SUBTLE,
        zeroline=False,
        ticksuffix=ticksuffix,
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    return fig


def build_asset_unit_price_chart(chart_data):
    hover_data = chart_data[["Fecha hover", "Precio unitario hover"]]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["Fecha plot"],
            y=chart_data["Precio unitario"],
            customdata=hover_data,
            mode="lines",
            name="Precio Unitario",
            line={"color": "#2563EB", "width": 3, "shape": LINE_TYPE, "smoothing": 0.2},
            fill=None,
            hovertemplate=(
                "Fecha: %{customdata[0]}<br>"
                "Precio Unitario: %{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )
    return aplicar_estilo_chart_activo(fig)


def calcular_evolucion_activo_registrada(df_asset):
    if df_asset.empty:
        return pd.DataFrame(columns=["Fecha", "Capital invertido", "Valor actual", "Diferencia (%)"])
    df = df_asset.copy()
    df["_fecha_orden"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["_id_orden"] = pd.to_numeric(df["id"], errors="coerce").fillna(0)
    df = df.sort_values(["_fecha_orden", "id"], na_position="last")
    df["Capital invertido"] = pd.to_numeric(df["dinero_inicial"], errors="coerce").fillna(0.0)
    df["Valor actual"] = pd.to_numeric(df["valor_actual"], errors="coerce").fillna(0.0)
    df["Diferencia (%)"] = df.apply(
        lambda row: (
            (row["Valor actual"] - row["Capital invertido"]) / row["Capital invertido"] * 100
            if row["Capital invertido"]
            else 0.0
        ),
        axis=1,
    )
    df["Fecha"] = df["fecha"].astype(str)
    return df[[
        "Fecha",
        "Capital invertido",
        "Valor actual",
        "Diferencia (%)",
        "_fecha_orden",
        "_id_orden",
    ]]


def opciones_con_valor(opciones, valor):
    return opciones if valor in opciones else [*opciones, valor]


def ordenar_catalogo_por_uso(opciones, usos):
    return sorted(opciones, key=lambda nombre: (-usos.get(nombre, 0), nombre.lower()))


def normalizar_nombre_activo(valor):
    return " ".join(str(valor or "").strip().casefold().split())


def filtrar_por_activo(df, inversion):
    if df.empty or "inversion" not in df:
        return df.copy()
    clave = normalizar_nombre_activo(inversion)
    mask = df["inversion"].apply(normalizar_nombre_activo) == clave
    return df[mask].copy()


def unidades_firmadas(row):
    unidades = row.get("unidades") if hasattr(row, "get") else None
    if unidades is None or pd.isna(unidades):
        return None
    unidades = float(unidades or 0)
    return unidades if row["tipo"] == "Compra" else -unidades


def unidades_actuales_por_activo(df_ops, fecha=None):
    posiciones = {}
    if df_ops.empty:
        return posiciones
    ops = df_ops.copy()
    if fecha is not None:
        ops["_fecha_orden"] = pd.to_datetime(ops["fecha"], errors="coerce")
        fecha_limite = pd.to_datetime(fecha, errors="coerce")
        if not pd.isna(fecha_limite):
            ops = ops[ops["_fecha_orden"] <= fecha_limite]
    for _, row in ops.iterrows():
        unidades = unidades_firmadas(row)
        if unidades is None:
            continue
        clave = normalizar_nombre_activo(row["inversion"])
        posiciones[clave] = posiciones.get(clave, 0.0) + unidades
    return posiciones


def operaciones_con_posicion(df_ops):
    if df_ops.empty:
        return df_ops.copy()
    operaciones = df_ops.copy()
    operaciones["_fecha_orden"] = pd.to_datetime(operaciones["fecha"], errors="coerce")
    operaciones = operaciones.sort_values(["_fecha_orden", "id"], ascending=[True, True])
    posicion = 0.0
    tiene_posicion = False
    posiciones = []
    for _, row in operaciones.iterrows():
        unidades = unidades_firmadas(row)
        if unidades is not None:
            posicion += unidades
            tiene_posicion = True
        posiciones.append(posicion if tiene_posicion else None)
    operaciones["posicion_unidades"] = posiciones
    return operaciones


def render_asset_detail_metrics(df_asset, df_asset_ops, clave_activo):
    if df_asset.empty:
        return
    ultimo = df_asset.sort_values(["fecha", "id"]).iloc[-1]
    valor_actual = float(ultimo["valor_actual"] or 0)
    valor_inicial = float(ultimo["dinero_inicial"] or 0)
    balance = valor_actual - valor_inicial
    balance_pct = (balance / valor_inicial * 100) if valor_inicial else 0.0
    unidades = unidades_actuales_por_activo(df_asset_ops).get(clave_activo)
    color_balance = color_por_signo(balance)

    with ui.element("div").classes("asset-detail-metrics"):
        with ui.element("div").classes("asset-detail-metric"):
            ui.label("Valor actual").classes("asset-detail-metric-label")
            ui.label(formato_euros_sin_signo(valor_actual)).classes("asset-detail-metric-value")
        with ui.element("div").classes("asset-detail-metric"):
            ui.label("Valor inicial").classes("asset-detail-metric-label")
            ui.label(formato_euros_sin_signo(valor_inicial)).classes("asset-detail-metric-value")
        with ui.element("div").classes("asset-detail-metric"):
            ui.label("Balance").classes("asset-detail-metric-label")
            ui.label(
                f"{formato_porcentaje(balance_pct, signed=True)} ({formato_euros(balance)})"
            ).classes(f"asset-detail-metric-value {color_balance}")
        with ui.element("div").classes("asset-detail-metric"):
            ui.label("Part./acciones").classes("asset-detail-metric-label")
            ui.label(formato_unidades(unidades)).classes("asset-detail-metric-value")


def ultimas_valoraciones(df_inv):
    if df_inv.empty:
        return df_inv.copy()
    return df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")


def investment_metric_card(label, value, icon, value_color="text-gray-900", extra_class=""):
    with ui.card().classes(f"metric-card investment-summary-card {extra_class}"):
        ui.icon(icon).classes("investment-summary-icon")
        ui.label(label).classes("metric-label")
        ui.label(value).classes(f"metric-value {value_color}")


def investment_balance_card(dinero_inicial, valor_final):
    balance = valor_final - dinero_inicial
    balance_pct = (balance / dinero_inicial * 100) if dinero_inicial else 0.0
    color_ganancia = color_por_signo(balance)
    balance_class = "investment-summary-balance-positive" if balance >= 0 else "investment-summary-balance-negative"

    with ui.card().classes(f"metric-card investment-summary-card {balance_class}"):
        ui.icon("trending_up" if balance >= 0 else "trending_down").classes("investment-summary-icon")
        ui.label("Balance").classes("metric-label")
        with ui.row().classes("items-baseline gap-2"):
            ui.label(formato_porcentaje(balance_pct, signed=True)).classes(
                f"metric-value {color_ganancia}"
            )
            ui.label(formato_euros(balance)).classes(f"text-sm font-semibold {color_ganancia}")


def render_resumen_inversiones(df_inv):
    ultimas = ultimas_valoraciones(df_inv)
    valor_total = float(ultimas["valor_actual"].sum()) if not ultimas.empty else 0.0
    dinero_inicial = float(ultimas["dinero_inicial"].sum()) if not ultimas.empty else 0.0

    with ui.row().classes("w-full gap-4"):
        investment_metric_card("Valor total de las inversiones", formato_euros_sin_signo(valor_total), "account_balance_wallet")
        investment_metric_card("Dinero inicial invertido", formato_euros_sin_signo(dinero_inicial), "track_changes")
        investment_balance_card(dinero_inicial, valor_total)


def metadata_historica_activos(df_inv, df_activos):
    metadata = {}

    if not df_inv.empty:
        for _, row in ultimas_valoraciones(df_inv).iterrows():
            inversion = str(row["inversion"] or "").strip()
            if not inversion:
                continue
            metadata[normalizar_nombre_activo(inversion)] = {
                "inversion": inversion,
                "tipo_activo": row.get("tipo_activo") or "Sin clasificar",
                "fecha_valoracion": row.get("fecha"),
                "dinero_inicial": float(row.get("dinero_inicial") or 0),
                "valor_actual": float(row.get("valor_actual") or 0),
            }

    if not df_activos.empty:
        for _, row in df_activos.sort_values("inversion").iterrows():
            inversion = str(row["inversion"] or "").strip()
            if not inversion:
                continue
            clave = normalizar_nombre_activo(inversion)
            datos = metadata.setdefault(clave, {"inversion": inversion})
            datos["inversion"] = inversion
            datos["tipo_activo"] = row.get("tipo_activo") or datos.get("tipo_activo") or "Sin clasificar"

    return metadata


def construir_activos_historicos(df_inv, df_ops, df_activos):
    metadata = metadata_historica_activos(df_inv, df_activos)
    activos_claves = set(metadata)

    if not df_ops.empty and "inversion" in df_ops:
        activos_claves.update(
            normalizar_nombre_activo(valor)
            for valor in df_ops["inversion"].dropna()
            if str(valor or "").strip()
        )
    if not df_inv.empty and "inversion" in df_inv:
        activos_claves.update(
            normalizar_nombre_activo(valor)
            for valor in df_inv["inversion"].dropna()
            if str(valor or "").strip()
        )

    ops_por_activo = {}
    if not df_ops.empty:
        operaciones = df_ops.copy()
        operaciones["_clave_activo"] = operaciones["inversion"].apply(normalizar_nombre_activo)
        operaciones["importe_num"] = pd.to_numeric(operaciones["importe"], errors="coerce").fillna(0.0)
        for clave, grupo in operaciones.groupby("_clave_activo"):
            if not clave:
                continue
            grupo_ordenado = grupo.sort_values(["fecha", "id"])
            compras = grupo_ordenado[grupo_ordenado["tipo"] == "Compra"]["importe_num"].sum()
            ventas = grupo_ordenado[grupo_ordenado["tipo"] == "Venta"]["importe_num"].sum()
            ops_por_activo[clave] = {
                "compras": float(compras or 0),
                "ventas": float(ventas or 0),
                "fecha_operacion": grupo_ordenado.iloc[-1]["fecha"],
            }
            activos_claves.add(clave)

    filas = []
    for clave in sorted(activos_claves):
        if not clave:
            continue
        datos = metadata.get(clave, {})
        operaciones = ops_por_activo.get(clave)
        inversion = datos.get("inversion")
        if not inversion and operaciones is not None:
            coincidencias = df_ops[df_ops["inversion"].apply(normalizar_nombre_activo) == clave]
            inversion = coincidencias.iloc[0]["inversion"] if not coincidencias.empty else clave

        if operaciones is not None:
            dinero_inicial = operaciones["compras"]
            valor_abierto = max(float(datos.get("valor_actual") or 0), 0.0)
            valor_final = operaciones["ventas"] + valor_abierto
            fecha = datos.get("fecha_valoracion") or operaciones.get("fecha_operacion")
        else:
            dinero_inicial = float(datos.get("dinero_inicial") or 0)
            valor_final = float(datos.get("valor_actual") or 0)
            fecha = datos.get("fecha_valoracion")

        if dinero_inicial == 0 and valor_final == 0 and not fecha:
            continue

        filas.append({
            "inversion": inversion,
            "dinero_inicial": dinero_inicial,
            "valor_actual": valor_final,
            "fecha": fecha or "-",
            "tipo_activo": datos.get("tipo_activo") or "Sin clasificar",
        })

    return pd.DataFrame(filas).sort_values("inversion") if filas else pd.DataFrame(
        columns=["inversion", "dinero_inicial", "valor_actual", "fecha", "tipo_activo"]
    )


def distribucion_historica_por_tipo(activos_historicos):
    if activos_historicos.empty:
        return pd.DataFrame(columns=["Tipo de activo", "Dinero inicial invertido", "Valor final/actual"])
    resumen = (
        activos_historicos
        .assign(tipo_activo=activos_historicos["tipo_activo"].fillna("Sin clasificar").replace("", "Sin clasificar"))
        .groupby("tipo_activo", as_index=False)[["dinero_inicial", "valor_actual"]]
        .sum()
        .rename(columns={
            "tipo_activo": "Tipo de activo",
            "dinero_inicial": "Dinero inicial invertido",
            "valor_actual": "Valor final/actual",
        })
    )
    return resumen.sort_values("Dinero inicial invertido", ascending=False)


def build_historical_asset_type_chart(distribucion):
    dinero_inicial_hover = distribucion["Dinero inicial invertido"].apply(formato_euros_hover)
    valor_final_hover = distribucion["Valor final/actual"].apply(formato_euros_hover)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=distribucion["Tipo de activo"],
            y=distribucion["Dinero inicial invertido"],
            customdata=dinero_inicial_hover,
            name="Dinero inicial invertido",
            marker_color=COLOR_PRIMARY,
            hovertemplate="%{x}<br>Dinero inicial: %{customdata}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=distribucion["Tipo de activo"],
            y=distribucion["Valor final/actual"],
            customdata=valor_final_hover,
            name="Valor final/actual",
            marker_color=COLOR_POSITIVE,
            hovertemplate="%{x}<br>Valor final/actual: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        barmode="group",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(255,255,255,0)",
        legend_title_text="",
        separators=",.",
        hoverlabel={
            "align": "left",
            "bgcolor": "#FFFFFF",
            "bordercolor": COLOR_GRID_SUBTLE,
            "font": {"color": "#1E293B", "size": 13},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#F8FAFC",
        zeroline=False,
        ticksuffix="\u20ac",
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    return fig


def render_assets_summary_table(activos, df_inv, refresh, usuario, empty_message):
    if activos.empty:
        ui.label(empty_message).classes("text-gray-500")
        return

    with ui.element("div").classes("current-assets-scroll"):
        with ui.element("div").classes("current-assets-table"):
            with ui.element("div").classes("current-assets-header-row bg-white sticky top-0 z-20"):
                for label in ["Activo", "Balance", "Últ. registro", "Tipo", ""]:
                    header_classes = "current-assets-table-header bg-white"
                    if label in {"Balance", "Últ. registro"}:
                        header_classes += " current-assets-number"
                    ui.label(label).classes(header_classes)
            for _, row in activos.iterrows():
                dinero_inicial = float(row["dinero_inicial"] or 0)
                valor_actual = float(row["valor_actual"] or 0)
                balance_pct = (
                    (valor_actual - dinero_inicial) / dinero_inicial * 100
                    if dinero_inicial
                    else 0.0
                )
                with ui.element("div").classes("current-assets-row"):
                    ui.label(row["inversion"]).classes("current-assets-name")
                    ui.label(formato_porcentaje(balance_pct, signed=True)).classes(
                        f"current-assets-number font-semibold {color_por_signo(balance_pct)}"
                    )
                    ui.label(str(row["fecha"])).classes("current-assets-number font-semibold")
                    ui.label(row["tipo_activo"] or "Sin clasificar").classes("current-assets-badge")
                    with ui.element("div").classes("current-assets-action"):
                        chart_button = ui.button(
                            icon="show_chart",
                            on_click=lambda inversion=row["inversion"]: open_asset_detail_dialog(
                                inversion, df_inv, refresh, usuario
                            ),
                        ).props("flat round dense")
                        with chart_button:
                            ui.tooltip("Ver evolución del activo")


def open_asset_edit_dialog(df_inv, refresh, usuario):
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    cotizaciones = cargar_cotizaciones_activos(usuario)
    activos = (
        df_inv.sort_values(["fecha", "id"])
        .drop_duplicates("inversion", keep="last")
        .sort_values("inversion")
    )

    with ui.dialog() as dialog, ui.card().classes("dialog-card asset-edit-dialog bg-slate-50"):
        ui.label("Editar activos").classes("text-2xl font-semibold")
        ui.label(
            "Los cambios de aplicación y tipo se aplicarán a todos los registros históricos del activo."
        ).classes("text-sm text-gray-600")

        def set_card_flipped(estado, inner, girada):
            estado["girada"] = girada
            if girada:
                inner.classes(add="[transform:rotateY(180deg)]")
            else:
                inner.classes(remove="[transform:rotateY(180deg)]")
            inner.update()

        def reset_asset_card(fila):
            fila["aplicacion_select"].set_value(fila["aplicacion_guardada"])
            fila["tipo_select"].set_value(fila["tipo_guardado"])
            fila["ticker_input"].set_value(fila["ticker_guardado"])
            fila["divisa_input"].set_value(fila["divisa_guardada"])
            fila["ticker_validado"] = fila["ticker_guardado"]
            fila["ticker_search_button"].set_visibility(False)
            set_card_flipped(fila["estado"], fila["inner"], False)

        def update_logo_image(fila, logo_url):
            fallback_logo = url_avatar_fallback(fila["inversion"])
            logo_url = (logo_url or fallback_logo).strip()
            fila["imagen_avatar"].set_source(logo_url)
            fila["imagen_avatar"]._props["error-src"] = fallback_logo
            fila["imagen_avatar"].update()

        def save_asset(fila):
            inversion = fila["inversion"]
            aplicacion = fila["aplicacion_select"].value
            tipo_activo = fila["tipo_select"].value
            if not aplicacion or not tipo_activo:
                ui.notify(f"Selecciona aplicación y tipo para {inversion}.", color="warning")
                return
            ticker = (fila["ticker_input"].value or "").strip().upper()
            divisa = (fila["divisa_input"].value or "").strip().upper()
            if ticker and ticker != fila["ticker_validado"]:
                ui.notify(f"Valida el ticker/ISIN de {inversion} con la lupa antes de guardar.", color="warning")
                return
            if ticker and not divisa:
                ui.notify(f"Busca el ticker/ISIN de {inversion} para rellenar la divisa.", color="warning")
                return
            logo_url = (
                fila["logo_url_guardada"]
                if ticker and ticker == fila["logo_ticker_guardado"]
                else url_avatar_fallback(inversion)
            )

            actualizar_clasificacion_inversiones([(aplicacion, tipo_activo, inversion)], usuario)
            guardar_cotizaciones_activos(
                [
                    {
                        "inversion": inversion,
                        "ticker_yahoo": ticker,
                        "divisa_cotizacion": divisa,
                        "divisa_valoracion": "EUR",
                        "auto_update_enabled": bool(ticker),
                        "logo_url": logo_url,
                    }
                ],
                usuario,
            )

            fila["aplicacion_guardada"] = aplicacion
            fila["tipo_guardado"] = tipo_activo
            fila["ticker_guardado"] = ticker
            fila["divisa_guardada"] = divisa
            fila["logo_url_guardada"] = logo_url
            fila["logo_ticker_guardado"] = ticker if ticker else ""
            fila["broker_badge"].set_text(aplicacion)
            fila["tipo_badge"].set_text(tipo_activo)
            fila["metadata_label"].set_text(f"{ticker} · {divisa}" if ticker else "")
            fila["metadata_label"].set_visibility(bool(ticker))
            fila["manual_badge"].set_visibility(not bool(ticker))
            update_logo_image(fila, logo_url)
            set_card_flipped(fila["estado"], fila["inner"], False)
            ui.notify(f"{inversion}: activo actualizado.", color="positive")

        async def sync_logo_asset(fila):
            inversion = fila["inversion"]
            ticker = (fila["ticker_input"].value or "").strip().upper()
            if ticker and ticker != fila["ticker_validado"]:
                ui.notify(f"Valida el ticker/ISIN de {inversion} con la lupa antes de sincronizar el logo.", color="warning")
                return
            fila["logo_sync_button"].disable()
            fila["logo_sync_spinner"].set_visibility(True)
            try:
                resultado = await sincronizar_logo_activo(inversion, ticker, usuario)
            except Exception:
                ui.notify(f"No se pudo sincronizar el logo de {inversion}.", color="warning")
                return
            finally:
                fila["logo_sync_spinner"].set_visibility(False)
                fila["logo_sync_button"].enable()

            fila["logo_url_guardada"] = resultado.logo_url
            fila["logo_ticker_guardado"] = ticker if ticker else ""
            update_logo_image(fila, resultado.logo_url)
            if resultado.used_duckduckgo:
                ui.notify(f"{inversion}: logo sincronizado desde DuckDuckGo Icons.", color="positive")
            else:
                ui.notify(f"{inversion}: se usará el avatar generado.", color="info")

        with ui.element("div").classes("grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 w-full"):
            for _, row in activos.iterrows():
                inversion = row["inversion"]
                aplicacion_actual = row["aplicacion"] or ""
                tipo_actual = row["tipo_activo"] or "Sin clasificar"
                cotizacion = cotizaciones.get(inversion, {})
                ticker_actual = (cotizacion.get("ticker_yahoo", "") or "").strip().upper()
                divisa_actual = (cotizacion.get("divisa_cotizacion", "") or "").strip().upper()
                fallback_logo = url_avatar_fallback(inversion)
                logo_actual = (cotizacion.get("logo_url") or "").strip() or fallback_logo
                estado = {"girada": False}
                with ui.element("div").classes("group h-[230px] w-full [perspective:1000px]"):
                    inner = ui.element("div").classes(
                        "relative w-full h-full transition-transform duration-500 [transform-style:preserve-3d]"
                    )
                    with inner:
                        with ui.card().classes(
                            "absolute inset-0 [backface-visibility:hidden] bg-white border border-slate-200 "
                            "rounded-2xl shadow-sm hover:-translate-y-1 hover:shadow-md cursor-pointer "
                            "transition-all flex flex-col items-center justify-center text-center p-5"
                        ) as front_card:
                            with ui.column().classes("w-full items-center justify-center gap-3 mt-2"):
                                imagen_avatar = ui.image(logo_actual).props(
                                    f'error-src="{fallback_logo}"'
                                ).classes(
                                    "w-16 h-16 rounded-full shadow-sm object-contain bg-white"
                                )
                                ui.label(inversion).classes(
                                    "text-lg font-bold text-slate-900 leading-tight line-clamp-2"
                                )
                                metadata_label = ui.label(f"{ticker_actual} · {divisa_actual}").classes(
                                    "text-xs font-medium text-slate-500 mb-2"
                                )
                                metadata_label.set_visibility(bool(ticker_actual))
                                manual_badge = ui.label("✍️ Valoración manual").classes(
                                    "bg-slate-100 text-slate-500 text-[11px] font-medium px-2.5 py-1 rounded-full mb-2"
                                )
                                manual_badge.set_visibility(not bool(ticker_actual))
                                with ui.row().classes("w-full justify-center gap-2"):
                                    broker_badge = ui.label(aplicacion_actual or "Sin broker").classes(
                                        "bg-blue-50 text-blue-700 rounded-full px-3 py-1 text-xs font-bold truncate"
                                    )
                                    tipo_badge = ui.label(tipo_actual).classes(
                                        "bg-slate-100 text-slate-600 rounded-full px-3 py-1 text-xs font-bold truncate"
                                    )

                        with ui.card().classes(
                            "absolute inset-0 [backface-visibility:hidden] [transform:rotateY(180deg)] "
                            "bg-slate-50 border border-blue-200 rounded-2xl shadow-md flex flex-col p-3 "
                            "justify-between"
                        ):
                            with ui.column().classes("w-full gap-1.5"):
                                aplicacion_select = ui.select(
                                    opciones_con_valor(aplicaciones, aplicacion_actual),
                                    label="Aplicación",
                                    value=aplicacion_actual,
                                ).props("outlined dense").classes("w-full rounded-lg")
                                tipo_select = ui.select(
                                    opciones_con_valor(tipos_activo, tipo_actual),
                                    label="Tipo de activo",
                                    value=tipo_actual,
                                ).props("outlined dense").classes("w-full rounded-lg")
                                with ui.row().classes("w-full gap-2"):
                                    ticker_input = ui.input(
                                        label="Ticker / ISIN",
                                        value=ticker_actual,
                                        placeholder="SAN.MC",
                                    ).props("outlined dense").classes("flex-1 min-w-0 rounded-lg")
                                    with ticker_input.add_slot("append"):
                                        ticker_search_spinner = ui.spinner(size="sm").classes("text-blue-600")
                                        ticker_search_button = ui.button(icon="search", color="primary").props(
                                            "flat round dense"
                                        )
                                    ticker_search_spinner.set_visibility(False)
                                    ticker_search_button.set_visibility(False)
                                    divisa_input = ui.input(
                                        label="Divisa",
                                        value=divisa_actual,
                                        placeholder="-",
                                    ).props("outlined dense readonly").classes("w-24 rounded-lg bg-white")

                            fila = {
                                "inversion": inversion,
                                "estado": estado,
                                "inner": inner,
                                "aplicacion_select": aplicacion_select,
                                "tipo_select": tipo_select,
                                "ticker_input": ticker_input,
                                "divisa_input": divisa_input,
                                "ticker_search_spinner": ticker_search_spinner,
                                "ticker_search_button": ticker_search_button,
                                "ticker_validado": ticker_actual,
                                "aplicacion_guardada": aplicacion_actual,
                                "tipo_guardado": tipo_actual,
                                "ticker_guardado": ticker_actual,
                                "divisa_guardada": divisa_actual,
                                "logo_url_guardada": logo_actual,
                                "logo_ticker_guardado": ticker_actual if logo_actual else "",
                                "imagen_avatar": imagen_avatar,
                                "broker_badge": broker_badge,
                                "tipo_badge": tipo_badge,
                                "metadata_label": metadata_label,
                                "manual_badge": manual_badge,
                            }
                            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                                logo_sync_spinner = ui.spinner(size="sm").classes("text-[#64748B]")
                                logo_sync_spinner.set_visibility(False)
                                logo_sync_button = ui.button(icon="sync").props("flat round dense").classes(
                                    "text-[#64748B]"
                                )
                                fila["logo_sync_spinner"] = logo_sync_spinner
                                fila["logo_sync_button"] = logo_sync_button
                                ui.button(
                                    "Cancelar",
                                    icon="close",
                                    on_click=lambda e=None, fila=fila: reset_asset_card(fila),
                                ).props("flat no-caps dense").classes("text-slate-500")
                                ui.button(
                                    "Guardar",
                                    icon="check",
                                    color="primary",
                                    on_click=lambda e=None, fila=fila: save_asset(fila),
                                ).props("unelevated no-caps dense").classes("rounded-xl font-bold px-3")

                def sync_ticker_search_state(fila=fila):
                    ticker = (fila["ticker_input"].value or "").strip().upper()
                    fila["ticker_search_button"].set_visibility(bool(ticker) and ticker != fila["ticker_validado"])
                    if not ticker:
                        fila["divisa_input"].value = ""

                async def buscar_ticker_fila(fila=fila):
                    ticker = (fila["ticker_input"].value or "").strip()
                    if not ticker:
                        ui.notify("Indica el ticker o ISIN de Yahoo.", color="warning")
                        return
                    fila["ticker_search_button"].set_visibility(False)
                    fila["ticker_search_spinner"].set_visibility(True)
                    try:
                        resultado = await run.io_bound(buscar_info_ticker_yahoo, ticker)
                    finally:
                        fila["ticker_search_spinner"].set_visibility(False)
                    if resultado.error:
                        fila["ticker_validado"] = ""
                        fila["divisa_input"].value = ""
                        fila["ticker_search_button"].set_visibility(True)
                        ui.notify(resultado.error, color="warning")
                        return
                    fila["ticker_input"].value = resultado.ticker_yahoo
                    fila["divisa_input"].value = resultado.divisa or ""
                    fila["ticker_validado"] = resultado.ticker_yahoo
                    fila["ticker_search_button"].set_visibility(False)
                    ui.notify(
                        f"{fila['inversion']}: ticker validado"
                        + (f" en {resultado.divisa}." if resultado.divisa else "."),
                        color="positive",
                    )

                ticker_input.on_value_change(lambda _, fila=fila: sync_ticker_search_state(fila))
                ticker_input.on("keydown.enter", lambda _, fila=fila: buscar_ticker_fila(fila))
                ticker_search_button.on_click(lambda e=None, fila=fila: buscar_ticker_fila(fila))
                logo_sync_button.on_click(lambda e=None, fila=fila: sync_logo_asset(fila))
                front_card.on("click", lambda _, fila=fila: set_card_flipped(fila["estado"], fila["inner"], True))

        with ui.row().classes("w-full justify-end pt-4 mt-2 border-t border-slate-200"):
            ui.button("Cerrar", on_click=dialog.close).props("flat no-caps").classes("text-slate-500")
    dialog.open()


def render_catalog_preferences(usuario):
    with ui.tabs().props('dense no-caps align="left"').classes(
        "w-full px-6 bg-white border-b border-slate-100"
    ) as tabs:
        brokers_tab = ui.tab("brokers", label="Brokers")
        tipos_tab = ui.tab("tipos", label="Tipos de activo")

    with ui.tab_panels(tabs, value=brokers_tab).classes(
        "w-full flex-1 overflow-y-auto overflow-x-hidden bg-slate-50"
    ):
        with ui.tab_panel(brokers_tab).classes("p-0"):
            cotizaciones = cargar_cotizaciones_activos(usuario)

            def activos_por_catalogo(columna):
                df_activos = cargar_datos("activos", usuario)
                if df_activos.empty:
                    return {}
                agrupados = {}
                for _, row in df_activos.sort_values("inversion").iterrows():
                    nombre_catalogo = str(row[columna] or "").strip()
                    inversion = str(row["inversion"] or "").strip()
                    if nombre_catalogo and inversion:
                        logo_url = (cotizaciones.get(inversion, {}).get("logo_url") or "").strip()
                        agrupados.setdefault(nombre_catalogo, []).append({
                            "nombre": inversion,
                            "logo_url": logo_url,
                        })
                return agrupados

            def render_mini_logos(activos, cantidad):
                activos = list(activos or [])
                with ui.element("div").classes("mt-1 w-full"):
                    with ui.row().classes("flex items-center justify-center"):
                        activos_visibles = activos[:3]
                        for activo in activos_visibles:
                            nombre_activo = activo.get("nombre", "") if isinstance(activo, dict) else str(activo)
                            fallback_logo = url_avatar_fallback(nombre_activo)
                            logo_url = (
                                activo.get("logo_url", "") if isinstance(activo, dict) else ""
                            ) or fallback_logo
                            ui.image(logo_url).props(f'error-src="{fallback_logo}"').classes(
                                "w-6 h-6 rounded-full border-2 border-white -ml-2 first:ml-0"
                            )
                        restantes = cantidad - len(activos_visibles) if cantidad > 3 else 0
                        if restantes:
                            with ui.element("div").classes(
                                "w-6 h-6 rounded-full border-2 border-white bg-slate-100 text-slate-600 "
                                "flex items-center justify-center text-[9px] font-bold -ml-2"
                            ):
                                ui.label(f"+{restantes}").classes("text-[9px] font-bold leading-none")

            def render_catalog_card(tabla, nombre, cantidad, activos, render_catalog):
                with ui.card().classes(
                    "bg-white rounded-2xl p-4 shadow-sm border border-slate-200 hover:-translate-y-1 "
                    "hover:shadow-md transition-all flex flex-col items-center text-center relative "
                    "aspect-square justify-between min-h-[160px]"
                ):
                    if cantidad == 0:
                        ui.button(
                            icon="delete",
                            on_click=lambda nombre=nombre: delete_catalog_item(
                                tabla, nombre, render_catalog, usuario
                            ),
                        ).props("flat dense round size=sm").classes(
                            "catalog-delete-button absolute top-2.5 right-2.5"
                        )
                    with ui.column().classes("w-full items-center gap-1 pt-3 min-w-0"):
                        ui.image(url_catalog_avatar(nombre)).classes(
                            "w-10 h-10 rounded-full mb-1 shadow-sm object-contain"
                        )
                        ui.label(nombre).classes(
                            "text-sm font-bold text-slate-900 line-clamp-1 w-full"
                        )
                        render_mini_logos(activos, cantidad)

            @ui.refreshable
            def render_brokers():
                usos = usos_catalogo("aplicacion", usuario)
                activos_por_broker = activos_por_catalogo("aplicacion")
                creando, set_creando = ui.state(False)
                with ui.grid().classes("catalog-preferences-grid grid-cols-2 gap-4 w-full p-6"):
                    for nombre in ordenar_catalogo_por_uso(cargar_catalogo("brokers"), usos):
                        activos = activos_por_broker.get(nombre, [])
                        cantidad = max(usos.get(nombre, 0), len(activos))
                        render_catalog_card("brokers", nombre, cantidad, activos, render_brokers)

                    brokers = set(cargar_catalogo("brokers"))
                    cuentas = [cuenta for cuenta in cargar_catalogo("cuentas") if cuenta not in brokers]
                    if not creando:
                        with ui.element("div").classes(
                            "catalog-create-card border-2 border-dashed border-slate-300 rounded-2xl "
                            "flex flex-col items-center justify-center cursor-pointer hover:bg-slate-50 "
                            "aspect-square min-h-[160px] transition-colors"
                        ) as ghost_card:
                            ghost_card.on("click", lambda _: set_creando(True))
                            ui.icon("add").classes(
                                "catalog-create-icon text-5xl"
                            )
                    else:
                        with ui.card().classes(
                            "bg-white border-2 border-blue-500 shadow-lg rounded-2xl flex flex-col "
                            "justify-between p-4 aspect-square min-h-[160px] transition-all min-w-0"
                        ):
                            ui.label("Añadir Broker").classes(
                                "text-sm font-bold text-slate-800 text-center w-full mb-2"
                            )
                            if not cuentas:
                                ui.label("No hay cuentas disponibles.").classes(
                                    "text-xs font-medium text-slate-500 text-center"
                                )
                                ui.button(
                                    "Cancelar",
                                    on_click=lambda: set_creando(False),
                                ).props("unelevated no-caps").classes(
                                    "w-full mt-auto bg-slate-100 text-slate-600 rounded-xl font-medium"
                                )
                            else:
                                cuenta_select = ui.select(
                                    cuentas,
                                    label="Cuenta",
                                    value=cuentas[0],
                                ).props("outlined dense").classes("w-full")

                                def add_broker():
                                    nombre = (cuenta_select.value or "").strip()
                                    if not nombre:
                                        ui.notify("Selecciona una cuenta.", color="warning")
                                        return
                                    try:
                                        insertar_catalogo("brokers", nombre)
                                    except sqlite3.IntegrityError:
                                        ui.notify("Ese broker ya existe.", color="warning")
                                        return
                                    set_creando(False)

                                with ui.row().classes("w-full grid grid-cols-2 gap-2 mt-auto pt-2 min-w-0"):
                                    ui.button(
                                        "Cancelar",
                                        on_click=lambda: set_creando(False),
                                    ).props("unelevated no-caps").classes(
                                        "bg-slate-100 text-slate-600 rounded-xl font-medium"
                                    )
                                    ui.button(
                                        "Guardar",
                                        on_click=add_broker,
                                    ).props("unelevated no-caps").classes(
                                        "bg-blue-600 text-white rounded-xl font-medium"
                                    )

            render_brokers()

        with ui.tab_panel(tipos_tab).classes("p-0"):
            @ui.refreshable
            def render_tipos():
                usos = usos_catalogo("tipo_activo", usuario)
                activos_por_tipo = activos_por_catalogo("tipo_activo")
                creando, set_creando = ui.state(False)
                with ui.grid().classes("catalog-preferences-grid grid-cols-2 gap-4 w-full p-6"):
                    for nombre in ordenar_catalogo_por_uso(cargar_catalogo("tipos_activo"), usos):
                        activos = activos_por_tipo.get(nombre, [])
                        cantidad = max(usos.get(nombre, 0), len(activos))
                        render_catalog_card("tipos_activo", nombre, cantidad, activos, render_tipos)

                    if not creando:
                        with ui.element("div").classes(
                            "catalog-create-card border-2 border-dashed border-slate-300 rounded-2xl "
                            "flex flex-col items-center justify-center cursor-pointer hover:bg-slate-50 "
                            "aspect-square min-h-[160px] transition-colors"
                        ) as ghost_card:
                            ghost_card.on("click", lambda _: set_creando(True))
                            ui.icon("add").classes(
                                "catalog-create-icon text-5xl"
                            )
                    else:
                        with ui.card().classes(
                            "bg-white border-2 border-blue-500 shadow-lg rounded-2xl flex flex-col "
                            "justify-between p-4 aspect-square min-h-[160px] transition-all min-w-0"
                        ):
                            ui.label("Añadir Tipo").classes(
                                "text-sm font-bold text-slate-800 text-center w-full mb-2"
                            )
                            nuevo_tipo = ui.input("Nuevo tipo de activo").props(
                                "outlined dense"
                            ).classes("w-full")

                            def add_tipo():
                                nombre = (nuevo_tipo.value or "").strip()
                                if not nombre:
                                    ui.notify("Indica un nombre.", color="warning")
                                    return
                                try:
                                    insertar_catalogo("tipos_activo", nombre)
                                except sqlite3.IntegrityError:
                                    ui.notify("Ese valor ya existe.", color="warning")
                                    return
                                set_creando(False)

                            with ui.row().classes("w-full grid grid-cols-2 gap-2 mt-auto pt-2 min-w-0"):
                                ui.button(
                                    "Cancelar",
                                    on_click=lambda: set_creando(False),
                                ).props("unelevated no-caps").classes(
                                    "bg-slate-100 text-slate-600 rounded-xl font-medium"
                                )
                                ui.button(
                                    "Guardar",
                                    on_click=add_tipo,
                                ).props("unelevated no-caps").classes(
                                    "bg-blue-600 text-white rounded-xl font-medium"
                                )

            render_tipos()


def open_preferences_drawer(usuario):
    with ui.dialog().props(
        'position="right" maximized transition-show="slide-left" transition-hide="slide-right"'
    ) as dialog, ui.card().classes(
        "preferences-drawer-card h-full bg-slate-50 p-0 flex flex-col no-shadow"
    ):
        with ui.row().classes(
            "w-full items-center justify-between p-6 bg-white border-b border-slate-100"
        ):
            ui.label("Preferencias").classes("text-2xl font-semibold text-slate-900")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes(
                "text-slate-500"
            )

        render_catalog_preferences(usuario)
    dialog.open()


def add_catalog_item(tabla, input_element, render_catalog):
    nombre = (input_element.value or "").strip()
    if not nombre:
        ui.notify("Indica un nombre.", color="warning")
        return
    try:
        insertar_catalogo(tabla, nombre)
    except sqlite3.IntegrityError:
        ui.notify("Ese valor ya existe.", color="warning")
        return
    input_element.value = ""
    render_catalog.refresh()


def delete_catalog_item(tabla, nombre, render_catalog, usuario=None):
    if not eliminar_catalogo(tabla, nombre, usuario):
        ui.notify("No se puede eliminar porque está siendo utilizado.", color="warning")
        return
    render_catalog.refresh()


def activo_predeterminado_operacion(df_inv, activos, usuario, opcion_nuevo):
    if not activos:
        return opcion_nuevo

    activos_positivos = set()
    if not df_inv.empty:
        ultimos = df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")
        activos_positivos.update(
            row["inversion"]
            for _, row in ultimos.iterrows()
            if float(row["valor_actual"] or 0) > 0
        )
    capitales = capitales_invertidos_por_activo(date.today().isoformat(), usuario)
    activos_positivos.update(
        inversion
        for inversion, capital in capitales.items()
        if float(capital or 0) > 0
    )
    n = len(activos_positivos) or len(activos)

    df_ops = cargar_datos("operaciones_inversion", usuario)
    if not df_ops.empty:
        operaciones = df_ops.sort_values(["fecha", "id"], ascending=[False, False])
        indice = max(0, min(n - 1, len(operaciones) - 1))
        inversion = operaciones.iloc[indice]["inversion"]
        if inversion in activos:
            return inversion

    for inversion in sorted(activos):
        if inversion in activos_positivos:
            return inversion
    return sorted(activos)[0]


def activos_operables(df_inv, usuario):
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    df_activos = cargar_datos("activos", usuario)
    activos = {}
    if not df_activos.empty:
        activos.update({
            row["inversion"]: {
                "aplicacion": row["aplicacion"] or (aplicaciones[0] if aplicaciones else ""),
                "tipo_activo": row["tipo_activo"] or (tipos_activo[0] if tipos_activo else "Sin clasificar"),
            }
            for _, row in df_activos.sort_values("inversion").iterrows()
        })
    if not df_inv.empty:
        ultimos = (
            df_inv.sort_values(["fecha", "id"])
            .drop_duplicates("inversion", keep="last")
            .sort_values("inversion")
        )
        activos.update({
            row["inversion"]: {
                "aplicacion": row["aplicacion"] or (aplicaciones[0] if aplicaciones else ""),
                "tipo_activo": row["tipo_activo"] or (tipos_activo[0] if tipos_activo else "Sin clasificar"),
            }
            for _, row in ultimos.iterrows()
        })
    return activos


def ultimo_valor_registrado_por_activo(df_inv):
    if df_inv.empty:
        return {}
    ultimos = df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")
    return {
        row["inversion"]: float(row["valor_actual"] or 0)
        for _, row in ultimos.iterrows()
    }


def build_operation_type_tabs(value="Compra", disabled=False):
    with ui.tabs(value=value).classes(
        "asset-chart-tabs operation-type-tabs bg-[#F8FAFC] rounded-full p-1 flex-1"
    ).props('dense no-caps active-color="dark" indicator-color="transparent"') as tipo_tabs:
        compra_tab = ui.tab("Compra", label="Compra")
        venta_tab = ui.tab("Venta", label="Venta")
        if disabled:
            compra_tab.disable()
            venta_tab.disable()
    return tipo_tabs


def style_operation_date_input(date_input, width_class="w-40"):
    return date_input.props("type=date outlined dense").classes(
        f"{width_class} operation-date-input rounded-lg"
    )


def style_operation_number_input(number_input, text_class="text-4xl", extra_props=""):
    props = f'outlined input-class="{text_class} font-medium text-right text-slate-900"'
    if extra_props:
        props = f"{extra_props} {props}"
    return number_input.props(props).classes("w-full operation-number-input bg-slate-50 rounded-xl border border-slate-200")


def build_operation_ticket_summary(tipo_select, importe_input, unidades_input, comisiones_input):
    with ui.column().classes("w-full bg-[#FFFFFF] border border-slate-100 rounded-xl px-4 py-3 gap-2 justify-center shadow-sm"):
        with ui.row().classes("justify-between w-full items-center"):
            ui.label("Precio medio").classes("text-xs font-semibold text-slate-500")
            precio_unitario_label = ui.label().classes("text-base font-semibold text-slate-900 text-right")
        with ui.row().classes("justify-between w-full items-center"):
            ui.label("Impacto en cuenta").classes("text-xs font-semibold text-slate-500")
            impacto_cuenta_label = ui.label().classes("text-base font-semibold text-right")

    def sync_ticket_summary():
        try:
            importe = float(importe_input.value or 0)
            unidades = float(unidades_input.value or 0)
        except (TypeError, ValueError):
            importe = 0
            unidades = 0
        try:
            comisiones = float(comisiones_input.value or 0)
        except (TypeError, ValueError):
            comisiones = 0
        precio_unitario_label.set_text(
            f"{formato_euros_sin_signo(importe / unidades)}/acción"
            if unidades > 0
            else "Pendiente"
        )
        impacto = -(importe + comisiones) if tipo_select.value == "Compra" else importe - comisiones
        impacto_cuenta_label.set_text(formato_euros(impacto))
        impacto_cuenta_label.classes(remove="text-[#10B981] text-[#F43F5E]")
        impacto_cuenta_label.classes(add="text-[#10B981]" if impacto >= 0 else "text-[#F43F5E]")

    importe_input.on_value_change(lambda _: sync_ticket_summary())
    unidades_input.on_value_change(lambda _: sync_ticket_summary())
    comisiones_input.on_value_change(lambda _: sync_ticket_summary())
    tipo_select.on_value_change(lambda _: sync_ticket_summary())
    sync_ticket_summary()
    return sync_ticket_summary


def asegurar_valor_catalogo(tabla, nombre):
    nombre = (nombre or "").strip()
    if not nombre or nombre in cargar_catalogo(tabla):
        return
    try:
        insertar_catalogo(tabla, nombre)
    except sqlite3.IntegrityError:
        pass


def open_existing_asset_dialog(df_inv, refresh, usuario):
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    activos = activos_operables(df_inv, usuario)
    opciones_activo = sorted(activos)
    if not opciones_activo:
        ui.notify("No hay activos existentes. Añade un nuevo activo primero.", color="warning")
        return

    df_ops = cargar_datos("operaciones_inversion", usuario)
    cotizaciones = cargar_cotizaciones_activos(usuario)
    ultimos_valores = ultimo_valor_registrado_por_activo(df_inv)
    posicion_actual = unidades_actuales_por_activo(df_ops)
    activo_default = activo_predeterminado_operacion(df_inv, activos, usuario, opciones_activo[0])
    if activo_default not in opciones_activo:
        activo_default = opciones_activo[0]

    with ui.dialog() as dialog, ui.card().classes("max-w-5xl w-full p-3 gap-3"):
        with ui.row().classes("w-full gap-4 items-start"):
            with ui.column().classes("flex-1 bg-[#F8FAFC] p-4 rounded-2xl gap-3 border border-slate-100"):
                ui.label("Operar con activo existente").classes("text-xl font-semibold text-slate-900")
                ui.label("Activo").classes("text-sm font-semibold text-slate-500")
                activo_select = ui.select(
                    opciones_activo,
                    value=activo_default,
                ).props("outlined dense").classes("w-full bg-white rounded-xl")

                with ui.row().classes("w-full gap-2 flex-wrap"):
                    broker_badge = ui.label().classes(
                        "rounded-full px-3 py-1 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100"
                    )
                    tipo_badge = ui.label().classes(
                        "rounded-full px-3 py-1 text-xs font-medium bg-slate-100 text-slate-700"
                    )

                with ui.column().classes("w-full bg-white border border-slate-200 rounded-xl p-4 shadow-sm gap-3"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Posición actual").classes("text-sm font-semibold text-slate-700")
                        feedback_spinner = ui.spinner(size="sm").classes("text-blue-600")
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        with ui.column().classes("gap-1 min-w-0"):
                            ui.label("TÍTULOS / UNIDADES").classes("text-[10px] uppercase font-bold tracking-wider text-slate-400")
                            position_units_label = ui.label().classes("text-base font-semibold text-slate-800")
                        with ui.column().classes("gap-1 min-w-0"):
                            ui.label("VALOR ESTIMADO").classes("text-[10px] uppercase font-bold tracking-wider text-slate-400")
                            position_value_label = ui.label().classes("text-base font-bold text-slate-900")
                    with ui.row().classes("items-center gap-1"):
                        unit_quote_label = ui.label().classes("text-[11px] font-medium text-slate-400")
                        unit_quote_icon = ui.icon("bolt").classes("text-[13px] text-blue-600")
                        unit_quote_source_label = ui.label("vía Yahoo Finance").classes(
                            "text-[10px] text-slate-400 font-medium"
                        )

            with ui.column().classes("flex-1 bg-[#FFFFFF] p-4 rounded-2xl gap-3 border border-slate-100 min-h-[430px]"):
                with ui.column().classes("w-full gap-3"):
                    with ui.row().classes("w-full gap-3 items-end"):
                        fecha_input = style_operation_date_input(ui.input(
                            "Fecha",
                            value=date.today().isoformat(),
                        ))
                        tipo_select = build_operation_type_tabs("Compra")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("IMPORTE TOTAL").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        importe_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=1,
                            suffix="€",
                        ))

                    with ui.column().classes("w-full gap-1"):
                        ui.label("UNIDADES").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        unidades_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=0.000001,
                            suffix="uds.",
                        ))

                    with ui.column().classes("w-full gap-1"):
                        ui.label("COMISIONES").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        comisiones_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=0.1,
                            suffix="€",
                        ), text_class="text-2xl")

                with ui.column().classes("w-full mt-auto gap-3"):
                    build_operation_ticket_summary(tipo_select, importe_input, unidades_input, comisiones_input)
                    ui.button("Registrar operación", on_click=lambda: save_existing_operation(), color="primary").props("unelevated no-caps size=lg").classes("w-full rounded-xl font-semibold text-base py-2 text-center")
                    ui.button("Cancelar", on_click=dialog.close, color="grey").props("flat no-caps dense").classes("w-full rounded-xl text-sm")

        async def sync_asset_feedback():
            inversion = activo_select.value
            if not inversion:
                feedback_spinner.set_visibility(False)
                broker_badge.set_text("-")
                tipo_badge.set_text("Sin clasificar")
                position_units_label.set_text("-")
                position_value_label.set_text("-")
                unit_quote_label.set_text("Cotización: -")
                unit_quote_icon.set_visibility(False)
                unit_quote_source_label.set_visibility(False)
                return
            clave = normalizar_nombre_activo(inversion)
            unidades = posicion_actual.get(clave, 0.0)
            datos_activo = activos.get(inversion, {})
            cotizacion = cotizaciones.get(inversion, {})
            ticker = cotizacion.get("ticker_yahoo", "")
            broker_badge.set_text(datos_activo.get("aplicacion") or "-")
            tipo_badge.set_text(datos_activo.get("tipo_activo") or "Sin clasificar")
            position_units_label.set_text(formato_unidades(unidades))
            if not ticker:
                feedback_spinner.set_visibility(False)
                ultimo_valor = ultimos_valores.get(inversion)
                position_value_label.set_text(formato_euros_sin_signo(ultimo_valor or 0))
                cotizacion_implicita = (float(ultimo_valor or 0) / unidades) if unidades > 0 else 0
                unit_quote_label.set_text(
                    f"Cotización: {formato_euros_sin_signo(cotizacion_implicita)} / ud."
                    if cotizacion_implicita > 0
                    else "Cotización: -"
                )
                unit_quote_icon.set_visibility(False)
                unit_quote_source_label.set_visibility(False)
                return

            feedback_spinner.set_visibility(True)
            position_value_label.set_text("Calculando...")
            unit_quote_label.set_text("Cotización: calculando...")
            unit_quote_icon.set_visibility(True)
            unit_quote_source_label.set_visibility(True)
            activo_consultado = inversion
            unidades_consulta = unidades if unidades > 0 else 1
            resultado = await run.io_bound(
                obtener_valor_mercado,
                inversion,
                ticker,
                unidades_consulta,
                date.today().isoformat(),
                cotizacion.get("divisa_cotizacion", ""),
                cotizacion.get("divisa_valoracion", "EUR"),
            )
            if activo_select.value != activo_consultado:
                return
            feedback_spinner.set_visibility(False)
            if resultado.error:
                ultimo_valor = ultimos_valores.get(inversion)
                position_value_label.set_text(formato_euros_sin_signo(ultimo_valor or 0))
                cotizacion_implicita = (float(ultimo_valor or 0) / unidades) if unidades > 0 else 0
                unit_quote_label.set_text(
                    f"Cotización: {formato_euros_sin_signo(cotizacion_implicita)} / ud."
                    if cotizacion_implicita > 0
                    else "Cotización: -"
                )
                unit_quote_icon.set_visibility(False)
                unit_quote_source_label.set_visibility(False)
                return
            precio_eur = float(resultado.valor_actual or 0) / unidades_consulta
            position_value_label.set_text(formato_euros_sin_signo(precio_eur * unidades))
            unit_quote_label.set_text(f"Cotización: {formato_euros_sin_signo(precio_eur)} / ud.")
            unit_quote_icon.set_visibility(True)
            unit_quote_source_label.set_visibility(True)

        activo_select.on_value_change(lambda _: sync_asset_feedback())
        ui.timer(0.1, sync_asset_feedback, once=True)

        def save_existing_operation():
            inversion = activo_select.value
            if not inversion:
                ui.notify("Selecciona el activo.", color="warning")
                return
            datos_activo = activos.get(inversion, {})
            aplicacion = datos_activo.get("aplicacion") or (aplicaciones[0] if aplicaciones else "")
            tipo_activo = datos_activo.get("tipo_activo") or (tipos_activo[0] if tipos_activo else "Sin clasificar")
            try:
                insertar_operacion_inversion(
                    fecha=fecha_input.value,
                    tipo=tipo_select.value,
                    inversion=inversion,
                    importe=importe_input.value,
                    cuenta=aplicacion,
                    aplicacion=aplicacion,
                    tipo_activo=tipo_activo,
                    usuario=usuario,
                    comisiones=comisiones_input.value,
                    unidades=unidades_input.value,
                )
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, f"{tipo_select.value} de {inversion} registrada correctamente.")
    dialog.open()


def open_new_asset_dialog(df_inv, refresh, usuario):
    modo_yahoo = "Automática"
    modo_manual = "Manual"
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    ticker_validado = {"ticker": "", "precio": None, "divisa": "", "logo_url": ""}
    modo_creacion_state = {"value": modo_yahoo}

    with ui.dialog() as dialog, ui.card().classes("max-w-5xl w-full p-3 gap-3"):
        with ui.row().classes("w-full gap-4 items-start"):
            with ui.column().classes("flex-1 bg-[#F8FAFC] p-4 rounded-2xl gap-3 border border-slate-100"):
                ui.label("Añadir nuevo activo").classes("text-xl font-semibold text-slate-900")
                ui.label("Definición del activo").classes("text-sm font-semibold text-slate-500")

                with ui.element("div").classes("bg-slate-100 p-1 rounded-xl w-full grid grid-cols-2 gap-1"):
                    with ui.element("div").classes("new-asset-mode-option rounded-lg p-3 cursor-pointer transition-colors") as automatic_mode_option:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("bolt").classes("text-lg")
                            ui.label("Auto").classes("text-sm font-semibold")
                        ui.label("Mercado / Yahoo Finance").classes("text-[11px] text-slate-500 mt-1")
                    with ui.element("div").classes("new-asset-mode-option rounded-lg p-3 cursor-pointer transition-colors") as manual_mode_option:
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("edit_note").classes("text-lg")
                            ui.label("Manual").classes("text-sm font-semibold")
                        ui.label("Inmuebles, efectivo, etc.").classes("text-[11px] text-slate-500 mt-1")

                with ui.column().classes("w-full gap-3") as automatic_container:
                    with ui.column().classes("w-full gap-1"):
                        ui.label("BUSCADOR").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                        ticker_cotizacion_input = ui.input(
                            placeholder="Ticker o ISIN",
                        ).props("outlined dense").classes("w-full bg-white rounded-xl")
                        with ticker_cotizacion_input.add_slot("append"):
                            search_button = ui.button(icon="search").props("flat round dense")
                        ticker_feedback = ui.label("").classes("text-xs text-[#10B981]")

                    with ui.row().classes("w-full bg-white border border-blue-100 rounded-xl p-4 shadow-sm items-center justify-between gap-3 flex-nowrap") as yahoo_confirmation_card:
                        with ui.column().classes("flex-1 min-w-0 gap-2 overflow-hidden"):
                            with ui.row().classes("w-full items-center gap-2 min-w-0 flex-nowrap overflow-hidden"):
                                yahoo_logo_fallback = url_avatar_fallback("Activo")
                                yahoo_asset_logo = ui.image(yahoo_logo_fallback).props(
                                    f'error-src="{yahoo_logo_fallback}"'
                                ).classes("w-9 h-9 rounded-full shadow-sm object-contain bg-white shrink-0 flex-none")
                                with ui.column().classes("flex-1 min-w-0 gap-1 overflow-hidden"):
                                    yahoo_asset_name_label = ui.label().classes("w-full min-w-0 text-sm font-semibold text-slate-900 truncate")
                                    yahoo_asset_meta_label = ui.label().classes(
                                        "w-full min-w-0 text-[9px] sm:text-[10px] text-slate-500 truncate leading-tight"
                                    )
                            yahoo_asset_price_label = ui.label().classes("text-xs font-semibold text-blue-700")
                        ui.icon("check_circle").classes("text-blue-600 text-xl shrink-0 flex-none")

                    with ui.column().classes("w-full bg-slate-50 border border-slate-200 rounded-2xl p-5 gap-4"):
                        with ui.column().classes("w-full gap-1"):
                            ui.label("BROKER / ENTIDAD").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                            auto_aplicacion_select = ui.select(
                                aplicaciones,
                                value=aplicaciones[0] if aplicaciones else None,
                            ).props("outlined dense").classes("w-full bg-white rounded-xl")
                        with ui.column().classes("w-full gap-1"):
                            ui.label("TIPO DE ACTIVO").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                            auto_tipo_activo_select = ui.select(
                                tipos_activo,
                                value=tipos_activo[0] if tipos_activo else None,
                            ).props("outlined dense").classes("w-full bg-white rounded-xl")

                with ui.column().classes("w-full bg-slate-50 border border-slate-200 rounded-2xl p-5 gap-4") as manual_container:
                    with ui.column().classes("w-full gap-1"):
                        ui.label("NOMBRE DEL ACTIVO").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                        nuevo_activo_input = ui.input(
                            placeholder="Ej. Vivienda alquiler, préstamo privado...",
                        ).props("outlined dense").classes("w-full bg-white rounded-xl")
                    with ui.column().classes("w-full gap-1"):
                        ui.label("BROKER / ENTIDAD").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                        manual_aplicacion_select = ui.select(
                            aplicaciones,
                            value=aplicaciones[0] if aplicaciones else None,
                        ).props("outlined dense").classes("w-full bg-white rounded-xl")
                    with ui.column().classes("w-full gap-1"):
                        ui.label("TIPO DE ACTIVO").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500")
                        manual_tipo_activo_select = ui.select(
                            tipos_activo,
                            value=tipos_activo[0] if tipos_activo else None,
                        ).props("outlined dense").classes("w-full bg-white rounded-xl")

                divisa_cotizacion_input = ui.input(value="EUR")
                divisa_cotizacion_input.set_visibility(False)

            with ui.column().classes("flex-1 bg-[#FFFFFF] p-4 rounded-2xl gap-3 border border-slate-100 min-h-[430px]"):
                with ui.column().classes("w-full gap-3"):
                    with ui.row().classes("w-full gap-3 items-end"):
                        fecha_input = style_operation_date_input(ui.input(
                            "Fecha",
                            value=date.today().isoformat(),
                        ))
                        tipo_select = build_operation_type_tabs("Compra", disabled=True)

                    with ui.column().classes("w-full gap-1"):
                        ui.label("IMPORTE TOTAL").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        importe_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=1,
                            suffix="€",
                        ))

                    with ui.column().classes("w-full gap-1"):
                        ui.label("UNIDADES").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        unidades_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=0.000001,
                            suffix="uds.",
                        ))

                    with ui.column().classes("w-full gap-1"):
                        ui.label("COMISIONES").classes("text-xs uppercase text-slate-500 font-bold tracking-wider")
                        comisiones_input = style_operation_number_input(ui.number(
                            value=0.0,
                            min=0,
                            step=0.1,
                            suffix="€",
                        ), text_class="text-2xl")

                with ui.column().classes("w-full mt-auto gap-3"):
                    build_operation_ticket_summary(tipo_select, importe_input, unidades_input, comisiones_input)
                    ui.button("Registrar operación", on_click=lambda: save_new_operation(), color="primary").props("unelevated no-caps size=lg").classes("w-full rounded-xl font-semibold text-base py-2 text-center")
                    ui.button("Cancelar", on_click=dialog.close, color="grey").props("flat no-caps dense").classes("w-full rounded-xl text-sm")

        async def buscar_ticker_nuevo_activo():
            ticker = (ticker_cotizacion_input.value or "").strip()
            if not ticker:
                ui.notify("Indica el ticker de Yahoo.", color="warning")
                return
            search_button.props(add="loading")
            ticker_feedback.set_text("Consultando Yahoo...")
            try:
                resultado = await run.io_bound(buscar_info_ticker_yahoo, ticker)
                if resultado.error:
                    ticker_validado.update({"ticker": "", "precio": None, "divisa": "", "logo_url": ""})
                    ticker_feedback.set_text("")
                    yahoo_confirmation_card.set_visibility(False)
                    ui.notify(resultado.error, color="warning")
                    return
                precio_resultado = await run.io_bound(
                    obtener_valor_mercado,
                    resultado.nombre or resultado.ticker_yahoo,
                    resultado.ticker_yahoo,
                    1,
                    fecha_input.value or date.today().isoformat(),
                    resultado.divisa,
                    "EUR",
                )
                logo_resultado = await obtener_logo_activo(
                    resultado.nombre or resultado.ticker_yahoo,
                    resultado.ticker_yahoo,
                )
            finally:
                search_button.props(remove="loading")

            if precio_resultado.error:
                ticker_validado.update({"ticker": "", "precio": None, "divisa": "", "logo_url": ""})
                ticker_feedback.set_text("")
                yahoo_confirmation_card.set_visibility(False)
                ui.notify(precio_resultado.error, color="warning")
                return
            nuevo_activo_input.value = resultado.nombre or resultado.ticker_yahoo
            divisa_cotizacion_input.value = resultado.divisa or "EUR"
            divisa_cotizacion_input.disable()
            precio = float(precio_resultado.valor_actual or 0)
            ticker_validado.update({
                "ticker": resultado.ticker_yahoo,
                "precio": precio,
                "divisa": resultado.divisa or "EUR",
                "logo_url": logo_resultado.logo_url,
            })
            logo_fallback = url_avatar_fallback(resultado.nombre or resultado.ticker_yahoo)
            yahoo_asset_logo.set_source(logo_resultado.logo_url)
            yahoo_asset_logo._props["error-src"] = logo_fallback
            yahoo_asset_logo.update()
            yahoo_asset_name_label.set_text(resultado.nombre or resultado.ticker_yahoo)
            yahoo_asset_meta_label.set_text(
                f"{resultado.ticker_yahoo} · {resultado.divisa or 'EUR'}"
            )
            yahoo_asset_price_label.set_text(
                f"Cotización actual: {formato_euros_sin_signo(precio)}"
            )
            yahoo_confirmation_card.set_visibility(True)
            ticker_feedback.set_text(f"Ticker válido. Precio actual: {formato_euros_sin_signo(precio)}")

        search_button.on_click(buscar_ticker_nuevo_activo)
        ticker_cotizacion_input.on("keydown.enter", lambda _: buscar_ticker_nuevo_activo())

        def sync_auto_ticker_state():
            ticker_actual_input = (ticker_cotizacion_input.value or "").strip().upper()
            if ticker_validado["ticker"] and ticker_actual_input != ticker_validado["ticker"]:
                ticker_validado.update({"ticker": "", "precio": None, "divisa": "", "logo_url": ""})
                ticker_feedback.set_text("")
                yahoo_confirmation_card.set_visibility(False)
                yahoo_logo_fallback = url_avatar_fallback("Activo")
                yahoo_asset_logo.set_source(yahoo_logo_fallback)
                yahoo_asset_logo._props["error-src"] = yahoo_logo_fallback
                yahoo_asset_logo.update()

        ticker_cotizacion_input.on_value_change(lambda _: sync_auto_ticker_state())

        def sync_creation_mode():
            automatico = modo_creacion_state["value"] == modo_yahoo
            automatic_container.set_visibility(automatico)
            manual_container.set_visibility(not automatico)
            active_classes = "bg-white shadow-sm text-blue-600 border border-blue-100"
            inactive_classes = "text-slate-500 border border-transparent"
            automatic_mode_option.classes(
                remove=inactive_classes if automatico else active_classes,
                add=active_classes if automatico else inactive_classes,
            )
            manual_mode_option.classes(
                remove=active_classes if automatico else inactive_classes,
                add=inactive_classes if automatico else active_classes,
            )
            if automatico:
                divisa_cotizacion_input.disable()
                yahoo_confirmation_card.set_visibility(bool(ticker_validado["ticker"]))
            else:
                ticker_validado.update({"ticker": "", "precio": None, "divisa": "", "logo_url": ""})
                ticker_feedback.set_text("")
                yahoo_confirmation_card.set_visibility(False)
                divisa_cotizacion_input.enable()

        def set_creation_mode(value):
            modo_creacion_state["value"] = value
            sync_creation_mode()

        sync_creation_mode()
        automatic_mode_option.on("click", lambda _: set_creation_mode(modo_yahoo))
        manual_mode_option.on("click", lambda _: set_creation_mode(modo_manual))

        def save_new_operation():
            inversion = (nuevo_activo_input.value or "").strip()
            if not inversion:
                ui.notify("Indica el activo de la operación.", color="warning")
                return
            if existe_nombre_activo(inversion, usuario):
                ui.notify(f"Ya existe el activo «{inversion}». Selecciónalo en la lista.", color="warning")
                return
            modo_creacion = modo_creacion_state["value"]
            guardar_cotizacion_nueva = modo_creacion == modo_yahoo
            divisa_cotizacion = (divisa_cotizacion_input.value or "").strip() if guardar_cotizacion_nueva else ""
            if guardar_cotizacion_nueva and not divisa_cotizacion:
                ui.notify("Indica la divisa del nuevo activo.", color="warning")
                return
            if guardar_cotizacion_nueva and ticker_validado["ticker"] != (ticker_cotizacion_input.value or "").strip().upper():
                ui.notify("Valida el ticker Yahoo con la lupa antes de guardar.", color="warning")
                return
            logo_url = ticker_validado["logo_url"] or url_avatar_fallback(inversion)
            aplicacion = auto_aplicacion_select.value if guardar_cotizacion_nueva else manual_aplicacion_select.value
            tipo_activo = auto_tipo_activo_select.value if guardar_cotizacion_nueva else manual_tipo_activo_select.value
            if not aplicacion or not tipo_activo:
                ui.notify("Selecciona broker y tipo de activo.", color="warning")
                return
            try:
                asegurar_valor_catalogo("brokers", aplicacion)
                asegurar_valor_catalogo("tipos_activo", tipo_activo)
                insertar_operacion_inversion(
                    fecha=fecha_input.value,
                    tipo="Compra",
                    inversion=inversion,
                    importe=importe_input.value,
                    cuenta=aplicacion,
                    aplicacion=aplicacion,
                    tipo_activo=tipo_activo,
                    usuario=usuario,
                    comisiones=comisiones_input.value,
                    unidades=unidades_input.value,
                )
                guardar_cotizaciones_activos(
                    [
                        {
                            "inversion": inversion,
                            "ticker_yahoo": ticker_validado["ticker"] if guardar_cotizacion_nueva else "",
                            "divisa_cotizacion": divisa_cotizacion,
                            "divisa_valoracion": "EUR",
                            "auto_update_enabled": guardar_cotizacion_nueva,
                            "logo_url": logo_url if guardar_cotizacion_nueva else "",
                        }
                    ],
                    usuario,
                )
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, f"Compra de {inversion} registrada correctamente.")
    dialog.open()


def open_investment_operation_edit_dialog(df_inv, refresh, usuario, operacion):
    modo_yahoo = "⚡ Automático (Yahoo)"
    modo_manual = "✍️ Manual"
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    df_activos = cargar_datos("activos", usuario)
    opcion_nuevo = "Nueva inversión"
    es_edicion = operacion is not None
    activos = {}
    if not df_activos.empty:
        activos.update({
            row["inversion"]: {
                "aplicacion": row["aplicacion"] or (aplicaciones[0] if aplicaciones else ""),
                "tipo_activo": row["tipo_activo"] or "Sin clasificar",
            }
            for _, row in df_activos.sort_values("inversion").iterrows()
        })
    if not df_inv.empty:
        ultimos = (
            df_inv.sort_values(["fecha", "id"])
            .drop_duplicates("inversion", keep="last")
            .sort_values("inversion")
        )
        activos.update({
            row["inversion"]: {
                "aplicacion": row["aplicacion"] or (aplicaciones[0] if aplicaciones else ""),
                "tipo_activo": row["tipo_activo"] or "Sin clasificar",
            }
            for _, row in ultimos.iterrows()
        })

    if es_edicion and operacion["inversion"] not in activos:
        activos[operacion["inversion"]] = {
            "aplicacion": aplicaciones[0] if aplicaciones else "",
            "tipo_activo": tipos_activo[0] if tipos_activo else "Sin clasificar",
        }

    opciones_activo = sorted(activos) + [opcion_nuevo]
    activo_default = (
        operacion["inversion"]
        if es_edicion
        else activo_predeterminado_operacion(df_inv, activos, usuario, opcion_nuevo)
    )
    with ui.dialog() as dialog, ui.card().classes("dialog-card max-w-4xl w-full p-6"):
        ui.label("Editar operación de inversión" if es_edicion else "Registrar operación de inversión").classes("text-2xl font-semibold")
        ui.label(
            "La operación crea también el movimiento de liquidez asociado en ingresos/gastos."
        ).classes("text-sm text-gray-600")

        with ui.row().classes("w-full gap-8 items-start mt-2"):
            with ui.column().classes("flex-1 gap-4"):
                with ui.row().classes("w-full gap-3"):
                    fecha_input = style_operation_date_input(ui.input(
                        "Fecha",
                        value=str(operacion["fecha"]) if es_edicion else date.today().isoformat(),
                    ))
                    tipo_select = build_operation_type_tabs(operacion["tipo"] if es_edicion else "Compra")

                activo_select = ui.select(
                    opciones_activo,
                    label="Activo",
                    value=activo_default,
                ).classes("w-full")

                with ui.card().classes("w-full bg-white border border-slate-200 rounded-xl p-4 gap-3") as nuevo_activo_card:
                    modo_creacion_toggle = ui.toggle(
                        [modo_yahoo, modo_manual],
                        value=modo_yahoo,
                    ).props("rounded unelevated spread no-caps").classes("w-full")

                    with ui.row().classes("w-full gap-2 items-center") as busqueda_yahoo_container:
                        ticker_cotizacion_input = ui.input(
                            "Ticker de Yahoo",
                            placeholder="SAN.MC",
                        ).classes("w-full")
                        with ticker_cotizacion_input.add_slot("append"):
                            search_button = ui.button(icon="search").props("flat round dense")

                    with ui.row().classes("w-full gap-3"):
                        nuevo_activo_input = ui.input("Nombre del activo").classes("flex-1")
                        divisa_cotizacion_input = ui.input(
                            "Divisa",
                            value="EUR",
                            placeholder="EUR",
                        ).classes("w-32")

                    with ui.row().classes("w-full gap-3"):
                        aplicacion_select = ui.select(
                            aplicaciones,
                            label="Broker",
                            value=aplicaciones[0] if aplicaciones else None,
                        ).classes("flex-1")
                        tipo_activo_select = ui.select(
                            tipos_activo,
                            label="Tipo de activo",
                            value=tipos_activo[0] if tipos_activo else None,
                        ).classes("flex-1")

            with ui.column().classes("flex-1 gap-4 bg-slate-50 border border-slate-200/80 p-5 rounded-2xl justify-between min-h-[380px]"):
                with ui.column().classes("w-full gap-4"):
                    importe_input = style_operation_number_input(ui.number(
                        "Importe (€)",
                        value=float(operacion["importe"]) if es_edicion else 0.0,
                        min=0,
                        step=1,
                    ), text_class="text-3xl")
                    unidades_valor = None
                    if es_edicion and "unidades" in operacion and not pd.isna(operacion["unidades"]):
                        unidades_valor = float(operacion["unidades"] or 0)
                    unidades_input = style_operation_number_input(ui.number(
                        "Acciones/participaciones *",
                        value=unidades_valor,
                        min=0,
                        step=0.000001,
                    ), text_class="text-3xl", extra_props="required")
                    comisiones_input = style_operation_number_input(ui.number(
                        "Comisiones (€)",
                        value=float(operacion["comisiones"] or 0) if es_edicion else 0.0,
                        min=0,
                        step=0.1,
                    ), text_class="text-3xl")

                with ui.column().classes("w-full bg-[#F8FAFC] border border-slate-100 p-3.5 rounded-xl text-center text-sm font-medium mt-auto gap-2"):
                    with ui.row().classes("justify-between w-full items-center"):
                        ui.label("Precio medio").classes("text-slate-600")
                        precio_unitario_label = ui.label().classes("font-semibold text-slate-900")
                    with ui.row().classes("justify-between w-full items-center"):
                        ui.label("Impacto en cuenta").classes("text-slate-600")
                        impacto_cuenta_label = ui.label().classes("font-semibold")

        async def buscar_ticker_nuevo_activo():
            ticker = (ticker_cotizacion_input.value or "").strip()
            if not ticker:
                ui.notify("Indica el ticker de Yahoo.", color="warning")
                return
            search_button.props(add="loading")
            try:
                resultado = await run.io_bound(buscar_info_ticker_yahoo, ticker)
            finally:
                search_button.props(remove="loading")
            if resultado.error:
                ui.notify(resultado.error, color="warning")
                return
            if resultado.nombre:
                nuevo_activo_input.value = resultado.nombre
            if resultado.divisa:
                divisa_cotizacion_input.value = resultado.divisa
            ui.notify("Datos del activo rellenados desde Yahoo.", color="positive")

        search_button.on_click(buscar_ticker_nuevo_activo)

        def sync_precio_unitario():
            try:
                importe = float(importe_input.value or 0)
                unidades = float(unidades_input.value or 0)
            except (TypeError, ValueError):
                unidades = 0
                importe = 0
            try:
                comisiones = float(comisiones_input.value or 0)
            except (TypeError, ValueError):
                comisiones = 0
            if unidades > 0:
                precio_unitario_label.set_text(
                    formato_euros_sin_signo(importe / unidades)
                )
            else:
                precio_unitario_label.set_text(
                    "Pendiente"
                )
            impacto = -(importe + comisiones) if tipo_select.value == "Compra" else importe - comisiones
            impacto_cuenta_label.set_text(formato_euros(impacto))
            impacto_cuenta_label.classes(remove="text-[#10B981] text-[#F43F5E]")
            impacto_cuenta_label.classes(add="text-[#10B981]" if impacto >= 0 else "text-[#F43F5E]")

        importe_input.on_value_change(lambda _: sync_precio_unitario())
        unidades_input.on_value_change(lambda _: sync_precio_unitario())
        comisiones_input.on_value_change(lambda _: sync_precio_unitario())
        tipo_select.on_value_change(lambda _: sync_precio_unitario())
        sync_precio_unitario()
        def sync_asset_fields():
            es_nuevo = activo_select.value == opcion_nuevo
            nuevo_activo_card.set_visibility(es_nuevo)
            aplicacion_select.enable() if es_nuevo else aplicacion_select.disable()
            tipo_activo_select.enable() if es_nuevo else tipo_activo_select.disable()
            if not es_nuevo and activo_select.value in activos:
                datos = activos[activo_select.value]
                if datos["aplicacion"]:
                    aplicacion_select.value = datos["aplicacion"]
                if datos["tipo_activo"]:
                    tipo_activo_select.value = datos["tipo_activo"]

        def sync_new_quote_fields():
            busqueda_yahoo_container.set_visibility(modo_creacion_toggle.value == modo_yahoo)

        sync_asset_fields()
        sync_new_quote_fields()
        activo_select.on_value_change(lambda _: sync_asset_fields())
        modo_creacion_toggle.on_value_change(lambda _: sync_new_quote_fields())

        def save_operation():
            es_nuevo = activo_select.value == opcion_nuevo
            inversion = (
                (nuevo_activo_input.value or "").strip()
                if es_nuevo
                else activo_select.value
            )
            if not inversion:
                ui.notify("Indica el activo de la operación.", color="warning")
                return
            if es_nuevo and existe_nombre_activo(inversion, usuario):
                ui.notify(f"Ya existe el activo «{inversion}». Selecciónalo en la lista.", color="warning")
                return
            modo_creacion = modo_creacion_toggle.value if es_nuevo else modo_manual
            divisa_cotizacion = (divisa_cotizacion_input.value or "").strip() if es_nuevo else ""
            guardar_cotizacion_nueva = es_nuevo and modo_creacion == modo_yahoo
            guardar_divisa_manual_nueva = es_nuevo and modo_creacion == modo_manual and bool(divisa_cotizacion)
            if es_nuevo and not divisa_cotizacion:
                ui.notify("Indica la divisa del nuevo activo.", color="warning")
                return
            if guardar_cotizacion_nueva:
                ticker_cotizacion = (ticker_cotizacion_input.value or "").strip()
                if not ticker_cotizacion:
                    ui.notify("Indica el ticker Yahoo del nuevo activo.", color="warning")
                    return
            if activo_select.value != opcion_nuevo and inversion in activos:
                aplicacion = activos[inversion]["aplicacion"] or aplicacion_select.value
                tipo_activo = activos[inversion]["tipo_activo"] or tipo_activo_select.value
            else:
                aplicacion = aplicacion_select.value
                tipo_activo = tipo_activo_select.value
            cuenta = aplicacion
            try:
                kwargs = {
                    "fecha": fecha_input.value,
                    "tipo": tipo_select.value,
                    "inversion": inversion,
                    "importe": importe_input.value,
                    "cuenta": cuenta,
                    "aplicacion": aplicacion,
                    "tipo_activo": tipo_activo,
                    "usuario": usuario,
                    "comisiones": comisiones_input.value,
                    "unidades": unidades_input.value,
                }
                if es_edicion:
                    actualizar_operacion_inversion(int(operacion["id"]), **kwargs)
                else:
                    insertar_operacion_inversion(**kwargs)
                if guardar_cotizacion_nueva or guardar_divisa_manual_nueva:
                    guardar_cotizaciones_activos(
                        [
                            {
                                "inversion": inversion,
                                "ticker_yahoo": ticker_cotizacion if guardar_cotizacion_nueva else "",
                                "divisa_cotizacion": divisa_cotizacion,
                                "divisa_valoracion": "EUR",
                                "auto_update_enabled": guardar_cotizacion_nueva,
                            }
                        ],
                        usuario,
                    )
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            mensaje = "Operación actualizada correctamente." if es_edicion else f"{tipo_select.value} de {inversion} registrada correctamente."
            refresh_view(refresh, mensaje)

        with ui.row().classes("w-full justify-end gap-3 mt-6 pt-4 border-t border-slate-100"):
            if es_edicion:
                def delete_operation():
                    try:
                        eliminar_operacion_inversion(int(operacion["id"]), usuario)
                    except ValueError as exc:
                        ui.notify(str(exc), color="warning")
                        return
                    dialog.close()
                    refresh_view(refresh, "Operación de inversión eliminada correctamente.")

                ui.button(icon="delete", on_click=delete_operation, color="negative").props("flat round")
            ui.button("Cancelar", on_click=dialog.close, color="grey").props("flat no-caps")
            ui.button("Guardar operación", icon="check_circle", on_click=save_operation, color="primary").props("unelevated no-caps size=lg").classes("rounded-xl font-semibold px-4 text-sm whitespace-nowrap")
    dialog.open()


def open_investment_entry_dialog(df_inv, refresh, usuario):
    df_activos = cargar_datos("activos", usuario)
    df_ops = cargar_datos("operaciones_inversion", usuario)
    cotizaciones = cargar_cotizaciones_activos(usuario)
    activos = {}
    if not df_activos.empty:
        for _, row in df_activos.sort_values("inversion").iterrows():
            activos[row["inversion"]] = {
                "inversion": row["inversion"],
                "aplicacion": row["aplicacion"] or "",
                "tipo_activo": row["tipo_activo"] or "Sin clasificar",
            }
    if not df_inv.empty:
        ultimos = df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")
        for _, row in ultimos.iterrows():
            activos[row["inversion"]] = {
                "inversion": row["inversion"],
                "aplicacion": row["aplicacion"] or activos.get(row["inversion"], {}).get("aplicacion", ""),
                "tipo_activo": row["tipo_activo"] or activos.get(row["inversion"], {}).get("tipo_activo", "Sin clasificar"),
            }
    filas = []

    def activos_valorables(fecha_valoracion):
        if not fecha_valoracion:
            return []
        capitales = capitales_invertidos_por_activo(fecha_valoracion, usuario)
        ultimos_valores = {}
        if not df_inv.empty:
            valoraciones = df_inv.copy()
            valoraciones["_fecha"] = pd.to_datetime(valoraciones["fecha"], errors="coerce")
            fecha_limite = pd.to_datetime(fecha_valoracion, errors="coerce")
            if not pd.isna(fecha_limite):
                valoraciones = valoraciones[valoraciones["_fecha"] <= fecha_limite]
            if not valoraciones.empty:
                ultimos = valoraciones.sort_values(["_fecha", "id"]).drop_duplicates("inversion", keep="last")
                ultimos_valores = {
                    row["inversion"]: float(row["valor_actual"] or 0)
                    for _, row in ultimos.iterrows()
                }
        return sorted(
            (
                {
                    **activo,
                    "dinero_inicial": float(capitales.get(activo["inversion"], 0.0) or 0.0),
                    "ultimo_valor": ultimos_valores.get(activo["inversion"]),
                }
                for activo in activos.values()
                if float(capitales.get(activo["inversion"], 0.0) or 0.0) > 0
            ),
            key=lambda item: (
                (item["aplicacion"] or "").lower(),
                (item["tipo_activo"] or "Sin clasificar").lower(),
                -float(item["dinero_inicial"] or 0),
                item["inversion"].lower(),
            ),
        )

    def valuation_currency_suffix(cotizacion):
        divisa = ((cotizacion or {}).get("divisa_valoracion") or "EUR").strip().upper()
        return {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}.get(divisa, divisa)

    autofill_button = None
    autofill_spinner = None
    selection_mode = {"active": False}

    async def run_autofill_entries():
        await autofill_entries()

    with ui.dialog() as dialog, ui.card().classes("dialog-card investment-entry-dialog"):
        ui.label("Actualizar valoración").classes("text-2xl font-semibold text-slate-900")

        with ui.row().classes("w-full justify-between items-center mb-4 gap-3"):
            fecha_input = ui.input("Fecha de registro", value=date.today().isoformat()).props(
                "type=date outlined dense color=blue-8"
            ).classes("w-52 operation-date-input rounded-lg")
            with fecha_input.add_slot("prepend"):
                ui.icon("event").classes("text-slate-400")

            with ui.row().classes("items-center gap-2"):
                autofill_spinner = ui.spinner(size="sm").classes("text-blue-600")
                autofill_spinner.set_visibility(False)
                autofill_button = ui.button(
                    "Rellenar automáticamente",
                    icon="auto_awesome",
                    on_click=run_autofill_entries,
                    color="primary",
                ).props("outline no-caps").classes(
                    "rounded-xl px-4 py-2 font-semibold text-[#2563EB] border border-blue-100 bg-blue-50/40 hover:bg-blue-50"
                )

        ui.separator().classes("w-full bg-slate-100")

        ui.label(
            "Completa el valor actual de mercado. Si el activo tiene compras o ventas registradas, el capital invertido se recalcula automáticamente."
        ).classes("text-sm text-slate-500")

        def sync_selection_controls():
            for fila in filas:
                fila["incluir"].set_visibility(selection_mode["active"])

        def toggle_selection_controls():
            selection_mode["active"] = not selection_mode["active"]
            sync_selection_controls()

        ui.button("Seleccionar", icon="checklist", on_click=toggle_selection_controls).props(
            "flat no-caps dense"
        ).classes(
            "self-start rounded-xl px-3 py-1.5 font-semibold text-[#2563EB] "
            "bg-blue-50/40 hover:bg-blue-50 border border-blue-100"
        )
        rows_container = ui.column().classes("w-full gap-3 investment-entry-rows")

        def add_existing_row(row):
            dinero_inicial = float(row["dinero_inicial"] or 0)
            ultimo_valor = row.get("ultimo_valor")
            cotizacion = cotizaciones.get(row["inversion"], {})
            ticker = (cotizacion.get("ticker_yahoo") or "").strip()
            fallback_logo = url_avatar_fallback(row["inversion"])
            logo_url = (cotizacion.get("logo_url") or "").strip() or fallback_logo
            with ui.element("div").classes(
                "investment-valuation-card bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
            ):
                with ui.row().classes("w-full items-center gap-3"):
                    incluir_checkbox = ui.checkbox(value=True).props("dense").classes("shrink-0")
                    incluir_checkbox.set_visibility(selection_mode["active"])
                    ui.image(logo_url).props(f'error-src="{fallback_logo}"').classes(
                        "w-10 h-10 rounded-full shadow-sm object-contain bg-white shrink-0"
                    )

                    with ui.column().classes("min-w-0 flex-[1.4] gap-1"):
                        with ui.row().classes("items-center gap-2 min-w-0"):
                            ui.label(row["inversion"]).classes("font-semibold text-slate-900 truncate")
                            if ticker:
                                ui.label(ticker).classes(
                                    "bg-slate-100 text-slate-500 rounded text-xs px-2 py-0.5 font-medium"
                                )
                        with ui.row().classes("items-center gap-2 text-xs text-slate-500"):
                            ui.label(row["tipo_activo"] or "Sin clasificar").classes("truncate")
                            ui.label("·").classes("text-slate-300")
                            ui.label(row["aplicacion"] or "Sin broker").classes("truncate")

                    with ui.row().classes("items-center gap-6 flex-[1.15] justify-end"):
                        with ui.column().classes("gap-0 items-end min-w-[120px]"):
                            ui.label("VALOR INICIAL").classes("text-[10px] uppercase font-bold tracking-wider text-slate-400")
                            ui.label(formato_euros_sin_signo(dinero_inicial)).classes("text-sm font-semibold text-slate-700")
                        with ui.column().classes("gap-0 items-end min-w-[140px]"):
                            ui.label("ÚLTIMO VALOR").classes("text-[10px] uppercase font-bold tracking-wider text-slate-400")
                            if ultimo_valor is None:
                                ui.label("-").classes("text-sm font-semibold text-slate-500")
                            else:
                                diferencia_ultimo = float(ultimo_valor or 0) - dinero_inicial
                                ui.label(formato_euros_sin_signo(float(ultimo_valor or 0))).classes(
                                    f"text-sm font-semibold {color_por_signo(diferencia_ultimo)}"
                                )

                    with ui.column().classes("w-44 gap-1"):
                        ui.label("VALOR ACTUAL").classes("text-[10px] uppercase font-bold tracking-wider text-slate-400 text-right")
                        valor_input = ui.number(
                            value=None,
                            min=0,
                            step=10,
                            suffix=valuation_currency_suffix(cotizacion),
                        ).props('outlined dense input-class="text-right"').classes(
                            "w-full operation-number-input rounded-xl bg-slate-50"
                        )
                        status_label = ui.label("").classes("text-xs text-gray-500")
            filas.append({
                "incluir": incluir_checkbox,
                "inversion": row["inversion"],
                "dinero": dinero_inicial,
                "valor": valor_input,
                "aplicacion": row["aplicacion"] or "",
                "tipo_activo": row["tipo_activo"] or "Sin clasificar",
                "cotizacion": cotizacion,
                "status": status_label,
            })

        @ui.refreshable
        def render_asset_rows():
            filas.clear()
            fecha_valoracion = fecha_input.value
            if not fecha_valoracion:
                ui.label("Indica una fecha para ver los activos con dinero invertido.").classes("text-gray-500")
                return
            activos_valoracion = activos_valorables(fecha_valoracion)
            if not activos_valoracion:
                ui.label(f"No hay activos con dinero invertido el {fecha_valoracion}.").classes("text-gray-500")
                return
            for row in activos_valoracion:
                add_existing_row(row)

        with rows_container:
            render_asset_rows()
        fecha_input.on_value_change(lambda _: render_asset_rows.refresh())

        def persist_entries(registros):
            upsert_inversiones_por_fecha_activo(registros, usuario)
            dialog.close()
            refresh_view(refresh, f"Registro actualizado para {len(registros)} activos.")

        def confirm_overwrite(registros, existentes):
            with ui.dialog() as confirm_dialog, ui.card().classes("dialog-card"):
                ui.label("Registros ya existentes").classes("text-xl font-semibold")
                ui.label(
                    "Ya existe un registro para la misma fecha y activo. "
                    "Si confirmas, se reescribirá el registro antiguo con los nuevos valores."
                ).classes("text-sm text-gray-600")
                for item in existentes:
                    ui.label(f"{item['fecha']} · {item['inversion']}").classes("text-sm")

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancelar", on_click=confirm_dialog.close, color="grey")

                    def overwrite():
                        confirm_dialog.close()
                        persist_entries(registros)

                    ui.button("Confirmar y reescribir", icon="save", on_click=overwrite, color="primary")
            confirm_dialog.open()

        async def autofill_entries():
            fecha = fecha_input.value
            if not fecha:
                ui.notify("Indica la fecha del registro.", color="warning")
                return
            if autofill_button:
                autofill_button.disable()
            if autofill_spinner:
                autofill_spinner.set_visibility(True)
            try:
                unidades_por_activo = unidades_actuales_por_activo(df_ops, fecha)
                rellenados = 0
                omitidos = 0
                errores = 0
                for fila in filas:
                    status = fila.get("status")
                    if status:
                        status.set_text("")
                    if not fila["incluir"].value:
                        omitidos += 1
                        continue
                    cotizacion = fila.get("cotizacion") or {}
                    ticker = cotizacion.get("ticker_yahoo")
                    if not ticker or not cotizacion.get("auto_update_enabled", True):
                        omitidos += 1
                        if status:
                            status.set_text("Sin ticker o auto desactivado")
                        continue
                    unidades = unidades_por_activo.get(normalizar_nombre_activo(fila["inversion"]), 0)
                    resultado = await run.io_bound(
                        obtener_valor_mercado,
                        fila["inversion"],
                        ticker,
                        unidades,
                        fecha,
                        cotizacion.get("divisa_cotizacion", ""),
                        cotizacion.get("divisa_valoracion", "EUR"),
                    )
                    if resultado.error:
                        errores += 1
                        if status:
                            status.set_text(resultado.error)
                        continue
                    fila["valor"].set_value(resultado.valor_actual)
                    rellenados += 1
                    if status:
                        status.set_text(
                            f"{resultado.ticker_yahoo} · {resultado.fecha_precio} · "
                            f"{formato_numero(resultado.precio)} {resultado.divisa_cotizacion}"
                        )
                ui.notify(
                    f"Autorrelleno: {rellenados} rellenados, {omitidos} omitidos, {errores} errores.",
                    color="positive" if rellenados else "warning",
                )
            finally:
                if autofill_spinner:
                    autofill_spinner.set_visibility(False)
                if autofill_button:
                    autofill_button.enable()

        def save_entries():
            fecha = fecha_input.value
            if not fecha:
                ui.notify("Indica la fecha del registro.", color="warning")
                return

            registros = []
            nombres = set()
            for fila in filas:
                if not fila["incluir"].value:
                    continue

                inversion = fila["inversion"]
                nombre_normalizado = inversion.strip().lower()
                if nombre_normalizado in nombres:
                    ui.notify(f"El activo «{inversion}» aparece más de una vez.", color="warning")
                    return
                nombres.add(nombre_normalizado)
                valor_actual = fila["valor"].value
                if valor_actual is None:
                    ui.notify(f"Indica el valor actual de mercado de {inversion}.", color="warning")
                    return

                registros.append((
                    fecha,
                    inversion,
                    float(fila["dinero"] or 0),
                    float(valor_actual),
                    fila["aplicacion"],
                    fila["tipo_activo"],
                ))

            if not registros:
                ui.notify("Añade al menos un activo al registro.", color="warning")
                return
            existentes = registros_inversion_existentes(registros, usuario)
            if existentes:
                confirm_overwrite(registros, existentes)
                return
            persist_entries(registros)

        with ui.row().classes("w-full justify-between items-center pt-4 mt-2 border-t border-slate-100"):
            ui.button("Cancelar", on_click=dialog.close, color="grey").props("flat no-caps").classes(
                "text-slate-500"
            )
            ui.button("Guardar Valoraciones", on_click=save_entries, color="primary").props(
                "unelevated no-caps"
            ).classes("bg-[#2563EB] text-white rounded-xl px-5 py-2 font-semibold")
    dialog.open()


def open_investment_record_edit_dialog(row, refresh, usuario):
    operacion_id = row.get("operacion_id") if hasattr(row, "get") else None
    registro_automatico = operacion_id not in (None, "") and operacion_id == operacion_id
    capital = capitales_invertidos_por_activo(str(row["fecha"]), usuario).get(
        row["inversion"],
        row["dinero_inicial"],
    )

    with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
        ui.label("Editar registro de valoración").classes("text-2xl font-semibold")
        ui.label(row["inversion"]).classes("text-lg font-semibold")

        with ui.row().classes("w-full gap-3"):
            fecha_input = ui.input("Fecha", value=str(row["fecha"])).props("type=date").classes("w-48")
            valor_input = ui.number(
                "Valor actual (€)",
                value=float(row["valor_actual"] or 0),
                min=0,
                step=10,
            ).classes("flex-1")

        with ui.row().classes("w-full gap-3"):
            ui.label(f"Tipo: {row['tipo_activo'] or 'Sin clasificar'}").classes("text-sm text-gray-600")
            ui.label(f"Aplicación: {row['aplicacion'] or ''}").classes("text-sm text-gray-600")
            ui.label(f"Valor inicial: {formato_euros_sin_signo(float(capital or 0))}").classes("text-sm text-gray-600")

        def save_record():
            if not fecha_input.value:
                ui.notify("Indica la fecha del registro.", color="warning")
                return
            if valor_input.value is None:
                ui.notify("Indica el valor actual.", color="warning")
                return
            try:
                actualizar_registro_inversion(
                    int(row["id"]),
                    fecha_input.value,
                    float(capital or 0),
                    float(valor_input.value),
                    row["aplicacion"] or "",
                    row["tipo_activo"] or "Sin clasificar",
                    usuario,
                )
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, "Registro de valoración actualizado correctamente.")

        def delete_record():
            try:
                eliminar_inversion(int(row["id"]), usuario)
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, "Registro de valoración eliminado correctamente.")

        with ui.row().classes("w-full justify-end gap-2"):
            delete_button = ui.button(icon="delete", on_click=delete_record, color="negative").props("flat round")
            if registro_automatico:
                delete_button.disable()
                with delete_button:
                    ui.tooltip("Este registro se generó automáticamente por una venta y no se puede eliminar.")
            ui.button("Cancelar", on_click=dialog.close, color="grey")
            ui.button("Guardar registro", icon="save", on_click=save_record, color="primary")
    dialog.open()


def open_asset_detail_dialog(inversion, df_inv, refresh, usuario):
    df_asset = filtrar_por_activo(df_inv, inversion)
    df_asset_ops = operaciones_con_posicion(
        filtrar_por_activo(cargar_datos("operaciones_inversion", usuario), inversion)
    )
    clave_activo = normalizar_nombre_activo(inversion)

    with ui.dialog() as dialog, ui.card().classes("dialog-card asset-detail-dialog"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label(inversion).classes("text-2xl font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        render_asset_detail_metrics(df_asset, df_asset_ops, clave_activo)

        with ui.element("div").classes("asset-detail-body"):
            if df_asset.empty:
                ui.label("No hay registros de valoración para este activo.").classes("text-gray-500")
            else:
                evolucion = calcular_evolucion_activo_registrada(df_asset)
                chart_data = preparar_evolucion_activo_chart(evolucion, df_asset_ops, clave_activo)
                with ui.element("div").classes("asset-detail-top"):
                    with ui.element("div").classes("asset-detail-chart-panel"):
                        with ui.column().classes("w-full gap-2"):
                            with ui.row().classes("w-full justify-end"):
                                with ui.tabs().classes(
                                    "asset-chart-tabs bg-[#F8FAFC] rounded-full p-1"
                                ).props(
                                    'dense no-caps active-color="dark" indicator-color="transparent"'
                                ) as asset_chart_tabs:
                                    position_tab = ui.tab("position", label="Posición")
                                    unit_price_tab = ui.tab("unit_price", label="Precio Unitario")

                            with ui.tab_panels(asset_chart_tabs, value=position_tab).classes(
                                "w-full asset-chart-panels"
                            ).props('animated transition-prev="fade" transition-next="fade"'):
                                with ui.tab_panel(position_tab).classes("asset-chart-tab-panel"):
                                    fig_position = build_investment_evolution_chart(evolucion)
                                    ui.plotly(prepare_chart(fig_position, 500)).classes(
                                        "plotly-chart asset-detail-plot"
                                    )
                                with ui.tab_panel(unit_price_tab).classes("asset-chart-tab-panel"):
                                    fig_unit_price = build_asset_unit_price_chart(chart_data)
                                    ui.plotly(prepare_chart(fig_unit_price, 500)).classes(
                                        "plotly-chart asset-detail-plot"
                                    )

                    with ui.element("div").classes("asset-detail-values-panel"):
                        with ui.element("div").classes("asset-detail-values-scroll"):
                            with ui.element("div").classes("asset-detail-values-table"):
                                ui.label("Fecha").classes("asset-detail-table-header")
                                ui.label("Valor").classes("asset-detail-table-header")
                                ui.label("Partic.").classes("asset-detail-table-header")
                                registros_tabla = evolucion.sort_values(
                                    ["_fecha_orden", "_id_orden"],
                                    ascending=[False, False],
                                    na_position="last",
                                )
                                for _, row in registros_tabla.iterrows():
                                    unidades_fecha = unidades_actuales_por_activo(
                                        df_asset_ops, row["Fecha"]
                                    ).get(clave_activo)
                                    ui.label(row["Fecha"])
                                    ui.label(formato_euros_sin_signo(float(row["Valor actual"] or 0))).classes(
                                        "font-semibold"
                                    )
                                    ui.label(formato_unidades(unidades_fecha)).classes("font-semibold")

            ui.label("Historial de operaciones").classes("section-title")
            if df_asset_ops.empty:
                ui.label("No hay operaciones registradas para este activo.").classes("text-gray-500")
            else:
                operaciones = df_asset_ops.sort_values(["fecha", "id"], ascending=[False, False])
                with ui.element("div").classes("asset-detail-operations-scroll"):
                    with ui.element("div").classes("asset-detail-operations-table"):
                        for label in ["Fecha", "Tipo", "Unidades", "Posición", "Importe", "Comisiones", ""]:
                            ui.label(label).classes("asset-detail-table-header")
                        for _, row in operaciones.iterrows():
                            ui.label(str(row["fecha"]))
                            ui.label(row["tipo"]).classes(
                                "font-semibold text-blue-700"
                                if row["tipo"] == "Compra"
                                else "font-semibold text-green-700"
                            )
                            ui.label(formato_unidades(row.get("unidades"))).classes("font-semibold")
                            ui.label(formato_unidades(row.get("posicion_unidades"))).classes("font-semibold")
                            ui.label(formato_euros_sin_signo(float(row["importe"] or 0)))
                            ui.label(formato_euros_sin_signo(float(row["comisiones"] or 0)))
                            ui.button(
                                icon="edit",
                                on_click=lambda row=row: open_investment_operation_edit_dialog(
                                    df_inv, refresh, usuario, row
                                ),
                            ).props("flat dense")
    dialog.open()


def open_historical_analysis_dialog(df_inv, df_ops, refresh, usuario):
    df_activos = cargar_datos("activos", usuario)
    activos_historicos = construir_activos_historicos(df_inv, df_ops, df_activos)
    distribucion = distribucion_historica_por_tipo(activos_historicos)
    dinero_inicial_total = (
        float(activos_historicos["dinero_inicial"].sum()) if not activos_historicos.empty else 0.0
    )
    valor_final_total = (
        float(activos_historicos["valor_actual"].sum()) if not activos_historicos.empty else 0.0
    )
    activos_totales = activos_historicos["inversion"].nunique() if not activos_historicos.empty else 0

    with ui.dialog() as dialog, ui.card().classes("dialog-card historical-analysis-dialog"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Análisis histórico").classes("text-2xl font-semibold")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        with ui.element("div").classes("historical-analysis-dialog-body"):
            with ui.row().classes("w-full gap-4"):
                investment_metric_card(
                    "Dinero inicial invertido",
                    formato_euros_sin_signo(dinero_inicial_total),
                    "track_changes",
                )
                investment_balance_card(dinero_inicial_total, valor_final_total)
                investment_metric_card(
                    "Activos totales distintos",
                    formato_numero(activos_totales, decimales=0),
                    "category",
                )

            if activos_historicos.empty:
                ui.label("Aún no hay inversiones registradas para analizar.").classes("text-gray-500")
            else:
                with ui.element("div").classes("historical-analysis-main"):
                    with ui.card().classes("chart-card historical-analysis-chart-card"):
                        ui.label("Capital y valor final por tipo de activo").classes("section-title")
                        if distribucion.empty:
                            ui.label("No hay datos suficientes para calcular la distribución.").classes("text-gray-500")
                        else:
                            fig_historico = build_historical_asset_type_chart(distribucion)
                            ui.plotly(prepare_chart(fig_historico, 460)).classes(
                                "plotly-chart historical-analysis-plot"
                            )

                    with ui.card().classes("chart-card historical-analysis-table-card"):
                        ui.label("Activos").classes("section-title")
                        render_assets_summary_table(
                            activos_historicos,
                            df_inv,
                            refresh,
                            usuario,
                            "Aún no hay activos registrados.",
                        )
    dialog.open()


def render_inversiones(refresh, usuario):
    df_inv = cargar_datos("inversiones", usuario)
    df_ops = cargar_datos("operaciones_inversion", usuario)

    def render_operation_history():
        if df_ops.empty:
            ui.label("Aún no hay operaciones de inversión registradas.").classes("text-gray-500")
            return
        operaciones = df_ops.sort_values(["fecha", "id"], ascending=[False, False])
        with ui.card().classes("table-card history-table-card"):
            with ui.element("div").classes("history-table-scroll"):
                with ui.element("div").classes("table-header investment-ops-table"):
                    for label in ["Fecha", "Tipo", "Activo", "Unidades", "Importe", "Comisiones", ""]:
                        ui.label(label).classes("font-semibold")
                for _, row in operaciones.iterrows():
                    with ui.element("div").classes("table-row investment-ops-table"):
                        ui.label(str(row["fecha"]))
                        ui.label(row["tipo"]).classes(
                            "font-semibold text-blue-700" if row["tipo"] == "Compra" else "font-semibold text-green-700"
                        )
                        ui.label(row["inversion"])
                        ui.label(formato_unidades(row.get("unidades"))).classes("font-semibold")
                        ui.label(formato_euros_sin_signo(float(row["importe"] or 0)))
                        ui.label(formato_euros_sin_signo(float(row["comisiones"] or 0)))
                        ui.button(
                            icon="edit",
                            on_click=lambda row=row: open_investment_operation_edit_dialog(df_inv, refresh, usuario, row),
                        ).props("flat dense")

    def render_record_history():
        if df_inv.empty:
            ui.label("Aún no hay valoraciones registradas.").classes("text-gray-500")
            return
        historial = df_inv.sort_values("fecha", ascending=False)
        for fecha, registros in historial.groupby("fecha", sort=False):
            ui.label(str(fecha)).classes("date-group")
            with ui.card().classes("table-card history-table-card"):
                with ui.element("div").classes("history-table-scroll"):
                    with ui.element("div").classes("table-header investments-table"):
                        for label in ["Inversión", "Tipo", "Inicial", "Valor actual", "Ganancia (%)", "Ganancia", "Aplicación", ""]:
                            ui.label(label).classes("font-semibold")
                    for _, row in registros.iterrows():
                        ganancia = row["valor_actual"] - row["dinero_inicial"]
                        ganancia_pct = (ganancia / row["dinero_inicial"] * 100) if row["dinero_inicial"] else 0.0
                        with ui.element("div").classes("table-row investments-table"):
                            ui.label(row["inversion"])
                            ui.label(row["tipo_activo"] or "Sin clasificar")
                            ui.label(formato_euros_sin_signo(row["dinero_inicial"]))
                            ui.label(formato_euros_sin_signo(row["valor_actual"]))
                            ui.label(formato_porcentaje(ganancia_pct, signed=True)).classes(f"font-semibold {color_por_signo(ganancia_pct)}")
                            ui.label(formato_euros(ganancia)).classes(f"font-semibold {color_por_signo(ganancia)}")
                            ui.label(row["aplicacion"])
                            ui.button(
                                icon="edit",
                                on_click=lambda row=row: open_investment_record_edit_dialog(row, refresh, usuario),
                            ).props("flat dense")

    def open_history_dialog():
        with ui.dialog() as dialog, ui.card().classes("dialog-card history-dialog"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("Historial").classes("text-2xl font-semibold")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense")

            with ui.tabs().classes("w-full") as history_tabs:
                operations_tab = ui.tab("operaciones", label="Historial de operaciones", icon="swap_horiz")
                records_tab = ui.tab("registros", label="Historial de registros", icon="fact_check")

            with ui.tab_panels(history_tabs, value=operations_tab).classes("w-full history-dialog-body"):
                with ui.tab_panel(operations_tab).classes("history-tab-panel"):
                    render_operation_history()
                with ui.tab_panel(records_tab).classes("history-tab-panel"):
                    render_record_history()
        dialog.open()

    ui.label("Seguimiento de Inversiones").classes("page-title")
    with ui.row().classes("w-full items-center justify-between"):
        with ui.row().classes("gap-3"):
            with ui.button("Registrar operación", icon="swap_horiz"):
                with ui.menu().classes("rounded-2xl p-2 min-w-[260px]") as operation_menu:
                    def open_existing_from_menu():
                        operation_menu.close()
                        with ui.context.client.content:
                            open_existing_asset_dialog(df_inv, refresh, usuario)

                    def open_new_from_menu():
                        operation_menu.close()
                        with ui.context.client.content:
                            open_new_asset_dialog(df_inv, refresh, usuario)

                    with ui.item(on_click=open_existing_from_menu).classes("rounded-xl px-3 py-2"):
                        with ui.item_section().props("avatar"):
                            ui.icon("swap_horiz").classes("text-[#2563EB]")
                        with ui.item_section():
                            ui.label("Operar con activo existente").classes("text-sm font-medium")
                    with ui.item(on_click=open_new_from_menu).classes("rounded-xl px-3 py-2"):
                        with ui.item_section().props("avatar"):
                            ui.icon("add_circle_outline").classes("text-[#2563EB]")
                        with ui.item_section():
                            ui.label("Añadir nuevo activo").classes("text-sm font-medium")
            ui.button(
                "Actualizar valoración",
                icon="add",
                on_click=lambda: open_investment_entry_dialog(df_inv, refresh, usuario),
            ).props("outline")
            if not df_inv.empty:
                ui.button(
                    "Editar activos",
                    icon="edit",
                    on_click=lambda: open_asset_edit_dialog(df_inv, refresh, usuario),
                ).props("outline")

    render_resumen_inversiones(df_inv)

    if df_inv.empty:
        ui.label("Aún no hay valoraciones registradas.").classes("text-gray-500")
    else:
        with ui.row().classes("w-full gap-4 items-stretch"):
            with ui.card().classes("chart-card"):
                ui.label("Evolución de la Cartera").classes("section-title")
                evolucion = calcular_evolucion_inversiones(df_inv)
                if not evolucion.empty:
                    fig = build_investment_evolution_chart(evolucion)
                    ui.plotly(prepare_chart(fig, 420)).classes("plotly-chart")

            with ui.card().classes("chart-card"):
                ui.label("Distribución actual por tipo de activo").classes("section-title")
                distribucion_tipos = calcular_distribucion_inversiones_por_tipo(df_inv)
                if distribucion_tipos.empty:
                    ui.label("No hay valores positivos para calcular la distribución.").classes("text-gray-500")
                else:
                    fig_tipos = px.pie(
                        distribucion_tipos,
                        names="Tipo de activo",
                        values="Valor actual",
                        hole=0.45,
                        color_discrete_sequence=CHART_COLORS,
                    )
                    fig_tipos.update_traces(textposition="inside", textinfo="percent+label")
                    fig_tipos.update_layout(showlegend=False)
                    ui.plotly(prepare_chart(fig_tipos, 420)).classes("plotly-chart")

        activos_actuales = ultimas_valoraciones(df_inv)
        if not activos_actuales.empty:
            activos_actuales = activos_actuales[activos_actuales["valor_actual"] > 0].copy()
            activos_actuales = activos_actuales.sort_values("inversion")

        with ui.row().classes("w-full gap-4 items-stretch"):
            with ui.card().classes("chart-card"):
                ui.label("Distribución de Inversiones").classes("section-title")
                if activos_actuales.empty:
                    ui.label("Aún no hay inversiones activas registradas.").classes("text-gray-500")
                else:
                    fig_activos = px.pie(
                        activos_actuales,
                        values="valor_actual",
                        names="inversion",
                        hole=0.4,
                        color_discrete_sequence=CHART_COLORS,
                    )
                    ui.plotly(prepare_chart(fig_activos, 420)).classes("plotly-chart")

            with ui.card().classes("chart-card"):
                ui.label("Activos actuales").classes("section-title")
                render_assets_summary_table(
                    activos_actuales,
                    df_inv,
                    refresh,
                    usuario,
                    "Aún no hay inversiones activas registradas.",
                )

    with ui.row().classes("w-full justify-center gap-3"):
        ui.button("Historial", icon="history", on_click=open_history_dialog).props("outline")
        ui.button(
            "Análisis histórico",
            icon="bar_chart",
            on_click=lambda: open_historical_analysis_dialog(df_inv, df_ops, refresh, usuario),
        ).props("outline")
