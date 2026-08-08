from datetime import date
import sqlite3

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

from db.queries import (
    actualizar_clasificacion_inversiones,
    actualizar_operacion_inversion,
    actualizar_registro_inversion,
    capitales_invertidos_por_activo,
    cargar_catalogo,
    cargar_datos,
    eliminar_catalogo,
    eliminar_inversion,
    eliminar_operacion_inversion,
    existe_nombre_activo,
    insertar_operacion_inversion,
    insertar_catalogo,
    registros_inversion_existentes,
    upsert_inversiones_por_fecha_activo,
    usos_catalogo,
)
from services.analytics import (
    calcular_distribucion_inversiones_por_tipo,
    calcular_evolucion_inversiones,
)
from ui.components import (
    color_por_signo,
    formato_euros,
    formato_euros_sin_signo,
    refresh_view,
)


COLOR_PRIMARY = "#2563EB"
COLOR_POSITIVE = "#10B981"
COLOR_NEGATIVE = "#F43F5E"
COLOR_SECONDARY = "#94A3B8"
CHART_COLORS = ["#3B82F6", "#06B6D4", "#8B5CF6", "#F97316", "#F43F5E"]


def prepare_chart(fig, height=520):
    fig.update_layout(
        autosize=True,
        height=height,
        margin={"l": 32, "r": 32, "t": 56, "b": 32},
    )
    return fig


def build_investment_evolution_chart(evolucion, title):
    evolucion_hover = evolucion.copy()
    evolucion_hover["Valor inicial hover"] = evolucion_hover["Capital invertido"].apply(
        formato_euros_sin_signo
    )
    evolucion_hover["Valor actual hover"] = evolucion_hover["Valor actual"].apply(
        formato_euros_sin_signo
    )
    evolucion_hover["Rentabilidad hover"] = evolucion_hover["Diferencia (%)"].apply(
        lambda valor: (
            f"<span style='color:{COLOR_POSITIVE if valor >= 0 else COLOR_NEGATIVE}'>"
            f"{'+' if valor > 0 else ''}{valor:.2f}%</span>"
        )
    )
    hover_data = evolucion_hover[
        ["Valor inicial hover", "Valor actual hover", "Rentabilidad hover"]
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=evolucion_hover["Fecha"],
            y=evolucion_hover["Capital invertido"],
            mode="lines+markers",
            name="Valor inicial",
            line={"color": COLOR_PRIMARY, "width": 2},
            marker={"size": 7},
            hoverinfo="none",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=evolucion_hover["Fecha"],
            y=evolucion_hover["Valor actual"],
            mode="lines+markers",
            name="Valor actual",
            line={"color": COLOR_POSITIVE, "width": 3},
            marker={"size": 7},
            fill="tozeroy",
            fillgradient={
                "type": "vertical",
                "colorscale": [
                    (0.0, "rgba(16, 185, 129, 0.00)"),
                    (1.0, "rgba(16, 185, 129, 0.20)"),
                ],
            },
            customdata=hover_data,
            hovertemplate=(
                "Valor inicial: %{customdata[0]}<br>"
                "Valor actual: %{customdata[1]}<br>"
                "Ganancia/pérdida: %{customdata[2]}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(ticksuffix="€")
    fig.update_xaxes(
        showspikes=True,
        spikecolor=COLOR_SECONDARY,
        spikethickness=1,
        spikemode="across",
        spikesnap="data",
    )
    fig.update_layout(
        title=title,
        plot_bgcolor="rgba(255,255,255,0)",
        paper_bgcolor="rgba(255,255,255,0)",
        legend_title_text="",
        hovermode="x unified",
        hoverlabel={"align": "left"},
    )
    fig.update_xaxes(gridcolor="rgba(148, 163, 184, 0.16)", zerolinecolor="rgba(148, 163, 184, 0.18)")
    fig.update_yaxes(gridcolor="rgba(148, 163, 184, 0.16)", zerolinecolor="rgba(148, 163, 184, 0.18)")
    return fig


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


def formato_unidades(valor):
    if valor is None or pd.isna(valor):
        return "-"
    valor = float(valor or 0)
    texto = f"{valor:.6f}".rstrip("0").rstrip(".")
    return texto or "0"


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
                f"{'+' if balance_pct > 0 else ''}{balance_pct:.2f}% ({formato_euros(balance)})"
            ).classes(f"asset-detail-metric-value {color_balance}")
        with ui.element("div").classes("asset-detail-metric"):
            ui.label("Part./acciones").classes("asset-detail-metric-label")
            ui.label(formato_unidades(unidades)).classes("asset-detail-metric-value")


def ultimas_valoraciones(df_inv):
    if df_inv.empty:
        return df_inv.copy()
    return df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")


def render_resumen_inversiones(df_inv):
    ultimas = ultimas_valoraciones(df_inv)
    valor_total = float(ultimas["valor_actual"].sum()) if not ultimas.empty else 0.0
    dinero_inicial = float(ultimas["dinero_inicial"].sum()) if not ultimas.empty else 0.0
    balance = valor_total - dinero_inicial
    ganancia_pct = (balance / dinero_inicial * 100) if dinero_inicial else 0.0
    color_ganancia = color_por_signo(balance)

    def investment_metric_card(label, value, icon, value_color="text-gray-900", extra_class=""):
        with ui.card().classes(f"metric-card investment-summary-card {extra_class}"):
            ui.icon(icon).classes("investment-summary-icon")
            ui.label(label).classes("metric-label")
            ui.label(value).classes(f"metric-value {value_color}")

    balance_class = "investment-summary-balance-positive" if balance >= 0 else "investment-summary-balance-negative"

    with ui.row().classes("w-full gap-4"):
        investment_metric_card("Valor total de las inversiones", formato_euros_sin_signo(valor_total), "account_balance_wallet")
        investment_metric_card("Dinero inicial invertido", formato_euros_sin_signo(dinero_inicial), "track_changes")
        with ui.card().classes(f"metric-card investment-summary-card {balance_class}"):
            ui.icon("trending_up" if balance >= 0 else "trending_down").classes("investment-summary-icon")
            ui.label("Balance").classes("metric-label")
            with ui.row().classes("items-baseline gap-2"):
                ui.label(f"{'+' if ganancia_pct > 0 else ''}{ganancia_pct:.2f}%").classes(
                    f"metric-value {color_ganancia}"
                )
                ui.label(formato_euros(balance)).classes(f"text-sm font-semibold {color_ganancia}")


def open_asset_edit_dialog(df_inv, refresh, usuario):
    aplicaciones = cargar_catalogo("brokers")
    tipos_activo = cargar_catalogo("tipos_activo")
    activos = (
        df_inv.sort_values(["fecha", "id"])
        .drop_duplicates("inversion", keep="last")
        .sort_values("inversion")
    )
    filas = []

    with ui.dialog() as dialog, ui.card().classes("dialog-card asset-edit-dialog"):
        ui.label("Editar activos").classes("text-2xl font-semibold")
        ui.label(
            "Los cambios de aplicación y tipo se aplicarán a todos los registros históricos del activo."
        ).classes("text-sm text-gray-600")

        with ui.element("div").classes("investment-entry-table"):
            with ui.element("div").classes("asset-edit-row investment-entry-header"):
                for label in ["Activo", "Aplicación (Broker)", "Tipo de activo"]:
                    ui.label(label)
            for _, row in activos.iterrows():
                inversion = row["inversion"]
                aplicacion_actual = row["aplicacion"] or ""
                tipo_actual = row["tipo_activo"] or "Sin clasificar"
                with ui.element("div").classes("asset-edit-row investment-entry-data"):
                    ui.label(inversion).classes("font-semibold investment-entry-text-cell")
                    aplicacion_select = ui.select(
                        opciones_con_valor(aplicaciones, aplicacion_actual),
                        value=aplicacion_actual,
                    )
                    tipo_select = ui.select(
                        opciones_con_valor(tipos_activo, tipo_actual),
                        value=tipo_actual,
                    )
                filas.append((inversion, aplicacion_actual, aplicacion_select, tipo_select))

        def save_assets():
            registros = []
            claves = set()
            for inversion, _, aplicacion_select, tipo_select in filas:
                if not aplicacion_select.value or not tipo_select.value:
                    ui.notify(f"Selecciona aplicación y tipo para {inversion}.", color="warning")
                    return
                clave = inversion.strip().lower()
                if clave in claves:
                    ui.notify(
                        f"No puede haber dos activos con el mismo nombre: {inversion}.",
                        color="negative",
                    )
                    return
                claves.add(clave)
                registros.append((aplicacion_select.value, tipo_select.value, inversion))
            actualizar_clasificacion_inversiones(registros, usuario)
            dialog.close()
            refresh_view(refresh, f"Clasificación actualizada para {len(registros)} activos.")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=dialog.close, color="grey")
            ui.button("Guardar cambios", icon="save", on_click=save_assets, color="primary")
    dialog.open()


def open_catalog_dialog(usuario):
    with ui.dialog() as dialog, ui.card().classes("dialog-card catalog-dialog"):
        ui.label("Modificar Brokers/Tipos").classes("text-2xl font-semibold")

        with ui.tabs().classes("w-full") as tabs:
            brokers_tab = ui.tab("brokers", label="Brokers")
            tipos_tab = ui.tab("tipos", label="Tipos de activo")

        with ui.tab_panels(tabs, value=brokers_tab).classes("w-full"):
            with ui.tab_panel(brokers_tab):
                @ui.refreshable
                def render_brokers():
                    usos = usos_catalogo("aplicacion", usuario)
                    with ui.element("div").classes("catalog-list"):
                        for nombre in ordenar_catalogo_por_uso(cargar_catalogo("brokers"), usos):
                            cantidad = usos.get(nombre, 0)
                            with ui.element("div").classes("catalog-row"):
                                ui.label(nombre).classes("font-semibold")
                                ui.label(f"{cantidad} activo{'s' if cantidad != 1 else ''}").classes("text-sm text-gray-500")
                                boton = ui.button(
                                    icon="delete",
                                    color="negative",
                                    on_click=lambda nombre=nombre: delete_catalog_item(
                                        "brokers", nombre, render_brokers, usuario
                                    ),
                                ).props("flat dense")
                                if cantidad:
                                    boton.disable()

                @ui.refreshable
                def render_broker_form():
                    brokers = set(cargar_catalogo("brokers"))
                    cuentas = [cuenta for cuenta in cargar_catalogo("cuentas") if cuenta not in brokers]
                    if not cuentas:
                        ui.label("No hay cuentas disponibles para crear nuevos brokers.").classes("text-gray-500")
                        return

                    with ui.row().classes("items-center gap-1"):
                        ui.label("Cuenta para nuevo broker").classes("text-sm font-semibold text-gray-700")
                        with ui.icon("info").classes("text-gray-500 cursor-help"):
                            ui.tooltip("Para crear un broker, primero tienes que crearlo como cuenta.")

                    cuenta_select = ui.select(
                        cuentas,
                        value=cuentas[0],
                    ).classes("w-full")

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
                        render_broker_form.refresh()
                        render_brokers.refresh()

                    ui.button("Añadir broker", icon="add", on_click=add_broker).props("outline")

                render_broker_form()
                render_brokers()

            with ui.tab_panel(tipos_tab):
                nuevo_tipo = ui.input("Nuevo tipo de activo").classes("w-full")

                @ui.refreshable
                def render_tipos():
                    usos = usos_catalogo("tipo_activo", usuario)
                    with ui.element("div").classes("catalog-list"):
                        for nombre in ordenar_catalogo_por_uso(cargar_catalogo("tipos_activo"), usos):
                            cantidad = usos.get(nombre, 0)
                            with ui.element("div").classes("catalog-row"):
                                ui.label(nombre).classes("font-semibold")
                                ui.label(f"{cantidad} activo{'s' if cantidad != 1 else ''}").classes("text-sm text-gray-500")
                                boton = ui.button(
                                    icon="delete",
                                    color="negative",
                                    on_click=lambda nombre=nombre: delete_catalog_item(
                                        "tipos_activo", nombre, render_tipos, usuario
                                    ),
                                ).props("flat dense")
                                if cantidad:
                                    boton.disable()

                def add_tipo():
                    add_catalog_item("tipos_activo", nuevo_tipo, render_tipos)

                ui.button("Añadir tipo", icon="add", on_click=add_tipo).props("outline")
                render_tipos()

        ui.button("Cerrar", on_click=dialog.close).classes("self-end")
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


def open_investment_operation_dialog(df_inv, refresh, usuario, operacion=None):
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
    with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
        ui.label("Editar operación de inversión" if es_edicion else "Registrar operación de inversión").classes("text-2xl font-semibold")
        ui.label(
            "La operación crea también el movimiento de liquidez asociado en ingresos/gastos."
        ).classes("text-sm text-gray-600")

        with ui.row().classes("w-full gap-3"):
            fecha_input = ui.input(
                "Fecha",
                value=str(operacion["fecha"]) if es_edicion else date.today().isoformat(),
            ).props("type=date").classes("w-48")
            tipo_select = ui.select(
                ["Compra", "Venta"],
                label="Tipo",
                value=operacion["tipo"] if es_edicion else "Compra",
            ).classes("w-48")

        with ui.row().classes("w-full gap-3 items-start"):
            activo_select = ui.select(
                opciones_activo,
                label="Activo",
                value=activo_default,
            ).classes("flex-1")
            nuevo_activo_input = ui.input("Nombre del nuevo activo").classes("flex-1")

        with ui.row().classes("w-full gap-3"):
            aplicacion_select = ui.select(
                aplicaciones,
                label="Aplicación (Broker)",
                value=aplicaciones[0] if aplicaciones else None,
            ).classes("flex-1")
            tipo_activo_select = ui.select(
                tipos_activo,
                label="Tipo de activo",
                value=tipos_activo[0] if tipos_activo else None,
            ).classes("flex-1")

        with ui.row().classes("w-full gap-3"):
            importe_input = ui.number(
                "Importe (€)",
                value=float(operacion["importe"]) if es_edicion else 0.0,
                min=0,
                step=1,
            ).classes("flex-1")
            unidades_valor = None
            if es_edicion and "unidades" in operacion and not pd.isna(operacion["unidades"]):
                unidades_valor = float(operacion["unidades"] or 0)
            unidades_input = ui.number(
                "Acciones/participaciones",
                value=unidades_valor,
                min=0,
                step=0.000001,
            ).classes("flex-1")
            comisiones_input = ui.number(
                "Comisiones (€)",
                value=float(operacion["comisiones"] or 0) if es_edicion else 0.0,
                min=0,
                step=0.1,
            ).classes("flex-1")

        precio_unitario_label = ui.label().classes("text-sm text-gray-600")

        def sync_precio_unitario():
            try:
                importe = float(importe_input.value or 0)
                unidades = float(unidades_input.value or 0)
            except (TypeError, ValueError):
                unidades = 0
                importe = 0
            if unidades > 0:
                precio_unitario_label.set_text(
                    f"Precio medio: {formato_euros_sin_signo(importe / unidades)} por acción/participación"
                )
            else:
                precio_unitario_label.set_text(
                    "Indica unidades si quieres seguir acciones/participaciones."
                )

        importe_input.on_value_change(lambda _: sync_precio_unitario())
        unidades_input.on_value_change(lambda _: sync_precio_unitario())
        sync_precio_unitario()

        def sync_asset_fields():
            es_nuevo = activo_select.value == opcion_nuevo
            nuevo_activo_input.set_visibility(es_nuevo)
            aplicacion_select.enable() if es_nuevo else aplicacion_select.disable()
            tipo_activo_select.enable() if es_nuevo else tipo_activo_select.disable()
            if not es_nuevo and activo_select.value in activos:
                datos = activos[activo_select.value]
                if datos["aplicacion"]:
                    aplicacion_select.value = datos["aplicacion"]
                if datos["tipo_activo"]:
                    tipo_activo_select.value = datos["tipo_activo"]

        sync_asset_fields()
        activo_select.on_value_change(lambda _: sync_asset_fields())

        def save_operation():
            inversion = (
                (nuevo_activo_input.value or "").strip()
                if activo_select.value == opcion_nuevo
                else activo_select.value
            )
            if not inversion:
                ui.notify("Indica el activo de la operación.", color="warning")
                return
            if activo_select.value == opcion_nuevo and existe_nombre_activo(inversion, usuario):
                ui.notify(f"Ya existe el activo «{inversion}». Selecciónalo en la lista.", color="warning")
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
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            mensaje = "Operación actualizada correctamente." if es_edicion else f"{tipo_select.value} de {inversion} registrada correctamente."
            refresh_view(refresh, mensaje)

        with ui.row().classes("w-full justify-end gap-2"):
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
            ui.button("Cancelar", on_click=dialog.close, color="grey")
            ui.button("Guardar operación", icon="save", on_click=save_operation, color="primary")
    dialog.open()


def open_investment_entry_dialog(df_inv, refresh, usuario):
    df_activos = cargar_datos("activos", usuario)
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

    with ui.dialog() as dialog, ui.card().classes("dialog-card investment-entry-dialog"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("Actualizar valoración").classes("text-2xl font-semibold")
            fecha_input = ui.input("Fecha de registro", value=date.today().isoformat()).props("type=date").classes("w-48")

        ui.label(
            "Completa el valor actual de mercado. Si el activo tiene compras o ventas registradas, el capital invertido se recalcula automáticamente."
        ).classes("text-sm text-gray-600")

        with ui.element("div").classes("investment-entry-table"):
            with ui.element("div").classes("investment-entry-row investment-entry-header"):
                with ui.element("div").classes("investment-entry-cell investment-entry-check-cell"):
                    ui.label("Incluir")
                for label in ["Activo", "Tipo de activo", "Aplicación (Broker)", "Valor inicial", "Último valor registrado", "Valor actual"]:
                    with ui.element("div").classes("investment-entry-cell"):
                        ui.label(label)

            rows_container = ui.element("div").classes("investment-entry-rows")

        def add_existing_row(row):
            dinero_inicial = float(row["dinero_inicial"] or 0)
            ultimo_valor = row.get("ultimo_valor")
            with ui.element("div").classes("investment-entry-row investment-entry-data"):
                with ui.element("div").classes("investment-entry-cell investment-entry-check-cell"):
                    incluir_checkbox = ui.checkbox(value=True)
                with ui.element("div").classes("investment-entry-cell investment-entry-text-cell"):
                    ui.label(row["inversion"]).classes("font-semibold")
                with ui.element("div").classes("investment-entry-cell investment-entry-text-cell"):
                    ui.label(row["tipo_activo"] or "Sin clasificar").classes("text-gray-700")
                with ui.element("div").classes("investment-entry-cell investment-entry-text-cell"):
                    ui.label(row["aplicacion"] or "").classes("text-gray-700")
                with ui.element("div").classes("investment-entry-cell investment-entry-text-cell"):
                    ui.label(formato_euros_sin_signo(dinero_inicial)).classes("text-gray-700")
                with ui.element("div").classes("investment-entry-cell investment-entry-text-cell"):
                    if ultimo_valor is None:
                        ui.label("-").classes("text-gray-700")
                    else:
                        diferencia_ultimo = float(ultimo_valor or 0) - dinero_inicial
                        ui.label(formato_euros_sin_signo(float(ultimo_valor or 0))).classes(
                            f"font-semibold {color_por_signo(diferencia_ultimo)}"
                        )
                with ui.element("div").classes("investment-entry-cell"):
                    valor_input = ui.number(value=None, min=0, step=10, suffix="€")
            filas.append({
                "incluir": incluir_checkbox,
                "inversion": row["inversion"],
                "dinero": dinero_inicial,
                "valor": valor_input,
                "aplicacion": row["aplicacion"] or "",
                "tipo_activo": row["tipo_activo"] or "Sin clasificar",
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

        with ui.row().classes("w-full justify-between items-center"):
            ui.label("Selecciona los activos que quieres valorar.").classes("text-sm text-gray-500")

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

            with ui.row().classes("gap-2"):
                ui.button("Cancelar", on_click=dialog.close, color="grey")
                ui.button("Guardar registro", icon="save", on_click=save_entries, color="primary")
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
                with ui.element("div").classes("asset-detail-top"):
                    with ui.element("div").classes("asset-detail-chart-panel"):
                        fig = build_investment_evolution_chart(
                            evolucion,
                            f"Evolución de {inversion}: Valor inicial vs. Valor actual",
                        )
                        ui.plotly(prepare_chart(fig, 500)).classes("plotly-chart asset-detail-plot")

                    with ui.element("div").classes("asset-detail-values-panel"):
                        with ui.element("div").classes("asset-detail-values-scroll"):
                            with ui.element("div").classes("asset-detail-values-table"):
                                ui.label("Fecha").classes("asset-detail-table-header")
                                ui.label("Valor").classes("asset-detail-table-header")
                                ui.label("Participaciones").classes("asset-detail-table-header")
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
                                on_click=lambda row=row: open_investment_operation_dialog(
                                    df_inv, refresh, usuario, row
                                ),
                            ).props("flat dense")
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
                            on_click=lambda row=row: open_investment_operation_dialog(df_inv, refresh, usuario, row),
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
                            ui.label(f"{'+' if ganancia_pct > 0 else ''}{ganancia_pct:.2f}%").classes(f"font-semibold {color_por_signo(ganancia_pct)}")
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
            ui.button(
                "Registrar operación",
                icon="swap_horiz",
                on_click=lambda: open_investment_operation_dialog(df_inv, refresh, usuario),
            )
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
        ui.button(
            "Modificar Brokers/Tipos",
            icon="settings",
            on_click=lambda: open_catalog_dialog(usuario),
        ).props("outline dense").classes("text-xs")

    render_resumen_inversiones(df_inv)

    if df_inv.empty:
        ui.label("Aún no hay valoraciones registradas.").classes("text-gray-500")
    else:
        with ui.row().classes("w-full gap-4 items-stretch"):
            with ui.card().classes("chart-card"):
                ui.label("Evolución de la Cartera").classes("section-title")
                evolucion = calcular_evolucion_inversiones(df_inv)
                if not evolucion.empty:
                    fig = build_investment_evolution_chart(
                        evolucion,
                        "Evolución del Patrimonio: Capital Invertido vs. Valor Actual",
                    )
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
                        title="Peso real por valor de mercado actual",
                        color_discrete_sequence=CHART_COLORS,
                    )
                    fig_tipos.update_traces(textposition="inside", textinfo="percent+label")
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
                if activos_actuales.empty:
                    ui.label("Aún no hay inversiones activas registradas.").classes("text-gray-500")
                else:
                    with ui.element("div").classes("current-assets-scroll"):
                        with ui.element("div").classes("current-assets-table"):
                            for label in ["Activo", "Balance", "Últ. registro", "Tipo", ""]:
                                header_classes = "current-assets-table-header"
                                if label in {"Balance", "Últ. registro"}:
                                    header_classes += " current-assets-number"
                                ui.label(label).classes(header_classes)
                            for _, row in activos_actuales.iterrows():
                                dinero_inicial = float(row["dinero_inicial"] or 0)
                                valor_actual = float(row["valor_actual"] or 0)
                                balance_pct = (
                                    (valor_actual - dinero_inicial) / dinero_inicial * 100
                                    if dinero_inicial
                                    else 0.0
                                )
                                with ui.element("div").classes("current-assets-row"):
                                    ui.label(row["inversion"]).classes("current-assets-name")
                                    ui.label(f"{'+' if balance_pct > 0 else ''}{balance_pct:.2f}%").classes(
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

    with ui.row().classes("w-full justify-center"):
        ui.button("Historial", icon="history", on_click=open_history_dialog).props("outline")
