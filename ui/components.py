import sqlite3

from nicegui import ui

from db.queries import (
    actualizar_transaccion,
    cargar_catalogo,
    cargar_datos,
    eliminar_catalogo,
    eliminar_transaccion,
    insertar_catalogo,
    insertar_transaccion,
    usos_catalogo,
)
from services.analytics import filtrar_transacciones, opciones_con_historial


def formato_euros(valor):
    signo = "+" if valor > 0 else ""
    return f"{signo}{valor:.2f}€"


def formato_euros_sin_signo(valor):
    return f"{valor:.2f}€"


def color_por_signo(valor):
    if valor > 0:
        return "text-positive"
    if valor < 0:
        return "text-negative"
    return "text-main"


def color_hex_por_signo(valor):
    if valor > 0:
        return "#10B981"
    if valor < 0:
        return "#F43F5E"
    return "#1E293B"


def color_por_tipo(tipo):
    if tipo == "Ingreso":
        return "text-positive"
    if tipo == "Gasto":
        return "text-negative"
    return "text-primary"


def actualizar_color_importe(input_element, valor=None):
    valor = input_element.value if valor is None else valor
    input_element.classes(remove="amount-positive amount-negative")
    try:
        importe = float(valor)
    except (TypeError, ValueError):
        return
    if importe > 0:
        input_element.classes(add="amount-positive")
    elif importe < 0:
        input_element.classes(add="amount-negative")


def metric_card(label, value, color="text-gray-900"):
    with ui.card().classes("metric-card"):
        ui.label(label).classes("metric-label")
        ui.label(value).classes(f"metric-value {color}")


def euro_label(valor, signed=True):
    texto = formato_euros(valor) if signed else formato_euros_sin_signo(valor)
    return ui.label(texto).classes(f"font-semibold {color_por_signo(valor)}")


def reload_page(message=None, color="positive", tab=None):
    if message:
        ui.notify(message, color=color)
    if tab:
        ui.navigate.to(f"/?tab={tab}")
    else:
        ui.navigate.reload()


def refresh_view(refresh, message, color="positive"):
    ui.notify(message, color=color)
    refresh()


def ordenar_catalogo_por_uso(opciones, usos):
    return sorted(opciones, key=lambda nombre: (-usos.get(nombre, 0), nombre.lower()))


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


def open_catalog_editor_dialog(
    *,
    titulo,
    tabla,
    columna_uso,
    input_label,
    add_button_label,
    count_singular="registro",
    count_plural="registros",
    usuario=None,
    on_close=None,
):
    with ui.dialog() as dialog, ui.card().classes("dialog-card catalog-dialog"):
        ui.label(titulo).classes("text-2xl font-semibold")
        nuevo_valor = ui.input(input_label).classes("w-full")

        @ui.refreshable
        def render_catalog():
            usos = usos_catalogo(columna_uso, usuario)
            with ui.element("div").classes("catalog-list"):
                for nombre in ordenar_catalogo_por_uso(cargar_catalogo(tabla), usos):
                    cantidad = usos.get(nombre, 0)
                    etiqueta = count_singular if cantidad == 1 else count_plural
                    with ui.element("div").classes("catalog-row"):
                        ui.label(nombre).classes("font-semibold")
                        ui.label(f"{cantidad} {etiqueta}").classes("text-sm text-gray-500")
                        boton = ui.button(
                            icon="delete",
                            color="negative",
                            on_click=lambda nombre=nombre: delete_catalog_item(
                                tabla, nombre, render_catalog, usuario
                            ),
                        ).props("flat dense")
                        if cantidad:
                            boton.disable()

        def add_item():
            add_catalog_item(tabla, nuevo_valor, render_catalog)

        def close_dialog():
            dialog.close()
            if on_close:
                on_close()

        nuevo_valor.on("keydown.enter", lambda _: add_item())
        ui.button(add_button_label, icon="add", on_click=add_item).props("outline")
        render_catalog()
        ui.button("Cerrar", on_click=close_dialog).classes("self-end")
    dialog.open()


def open_duplicate_dialog(data, refresh, usuario, on_confirm=None):
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        ui.label("Operación duplicada").classes("text-xl font-semibold")
        ui.label("Ya existe una operación con exactamente los mismos datos. Confirma si quieres registrarla de nuevo.")
        ui.label(
            f"{data['fecha']} · {data['tipo']} · {data['cuenta']} · {data['sector']} · {formato_euros(data['importe'])}"
        ).classes("text-sm text-gray-600")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("Cancelar", on_click=dialog.close, color="grey")

            def confirm_duplicate():
                insertar_transaccion(
                    data["fecha"],
                    data["tipo"],
                    data["descripcion"],
                    data["cuenta"],
                    data["sector"],
                    data["importe"],
                    usuario,
                )
                if on_confirm:
                    on_confirm()
                dialog.close()
                refresh_view(refresh, "Operación duplicada registrada correctamente.")

            ui.button("Confirmar duplicado", on_click=confirm_duplicate, color="primary")
    dialog.open()


def open_edit_transaction_dialog(row, refresh, usuario):
    df_tx = cargar_datos("transacciones", usuario)
    movimiento_id = int(row["id"])
    opciones_cuenta = opciones_con_historial(
        df_tx, "cuenta", cargar_catalogo("cuentas"), "Otra"
    )
    opciones_sector = opciones_con_historial(
        df_tx, "sector", cargar_catalogo("sectores"), "Otro"
    )

    with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
        ui.label("Editar movimiento").classes("text-xl font-semibold")
        fecha_input = ui.input("Fecha", value=str(row["fecha"])).props("type=date").classes("w-full")
        importe_input = ui.number(
            "Importe (€) - Positivo: Ingreso / Negativo: Gasto",
            value=float(row["importe"]),
            step=1,
        ).classes("w-full signed-amount-input")
        importe_input.on_value_change(lambda e: actualizar_color_importe(importe_input, e.value))
        actualizar_color_importe(importe_input)
        descripcion_input = ui.input("Descripción", value=row["descripcion"] or "").classes("w-full")

        with ui.row().classes("w-full gap-3"):
            cuenta_select = ui.select(opciones_cuenta, label="Cuenta", value=row["cuenta"]).classes("flex-1")
            nueva_cuenta = ui.input("Nueva cuenta").classes("flex-1")
            sector_select = ui.select(opciones_sector, label="Sector", value=row["sector"]).classes("flex-1")
            nuevo_sector = ui.input("Nuevo sector").classes("flex-1")

        nueva_cuenta.set_visibility(cuenta_select.value == "Otra")
        nuevo_sector.set_visibility(sector_select.value == "Otro")
        cuenta_select.on_value_change(lambda e: nueva_cuenta.set_visibility(e.value == "Otra"))
        sector_select.on_value_change(lambda e: nuevo_sector.set_visibility(e.value == "Otro"))

        def save():
            importe = float(importe_input.value or 0)
            if importe == 0:
                ui.notify("El importe no puede ser 0.", color="warning")
                return
            cuenta = (nueva_cuenta.value or "").strip() if cuenta_select.value == "Otra" else cuenta_select.value
            sector = (nuevo_sector.value or "").strip() if sector_select.value == "Otro" else sector_select.value
            if not cuenta or not sector:
                ui.notify("Indica la nueva cuenta o el nuevo sector.", color="warning")
                return
            tipo = "Ingreso" if importe > 0 else "Gasto"
            try:
                actualizar_transaccion(
                    movimiento_id,
                    fecha_input.value,
                    tipo,
                    descripcion_input.value or "",
                    cuenta,
                    sector,
                    importe,
                    usuario,
                )
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, "Movimiento actualizado correctamente.")

        def delete():
            try:
                eliminar_transaccion(movimiento_id, usuario)
            except ValueError as exc:
                ui.notify(str(exc), color="warning")
                return
            dialog.close()
            refresh_view(refresh, "Movimiento eliminado correctamente.")

        with ui.row().classes("justify-between w-full"):
            ui.button("Eliminar movimiento", icon="delete", on_click=delete, color="negative")
            with ui.row().classes("gap-2"):
                ui.button("Cancelar", on_click=dialog.close, color="grey")
                ui.button("Guardar cambios", icon="save", on_click=save, color="primary")
    dialog.open()


def open_sector_breakdown_dialog(df_tx, sector, fecha_inicio, fecha_fin=None):
    movimientos = filtrar_transacciones(df_tx, fecha_inicio, sector, fecha_fin)
    gastos = movimientos[movimientos["importe"] < 0]
    ingresos = movimientos[movimientos["importe"] > 0]

    with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
        ui.label(f"Desglose: {sector}").classes("text-xl font-semibold")
        with ui.row().classes("w-full gap-3"):
            metric_card("Gastos", formato_euros_sin_signo(abs(gastos["importe"].sum())), "text-red-700")
            metric_card("Ingresos", formato_euros_sin_signo(ingresos["importe"].sum()), "text-green-700")
            metric_card("Balance", formato_euros(movimientos["importe"].sum()), color_por_signo(movimientos["importe"].sum()))

        def render_detail(title, df):
            ui.label(title).classes("text-lg font-semibold mt-2")
            if df.empty:
                ui.label("No hay movimientos.").classes("text-gray-500")
                return
            columns = [
                {"name": "fecha", "label": "Fecha", "field": "fecha", "align": "left"},
                {"name": "descripcion", "label": "Descripción", "field": "descripcion", "align": "left"},
                {"name": "cuenta", "label": "Cuenta", "field": "cuenta", "align": "left"},
                {"name": "importe", "label": "Importe", "field": "importe_fmt", "align": "right"},
            ]
            rows = []
            for _, row in df.iterrows():
                rows.append({
                    "fecha": str(row["fecha"]),
                    "descripcion": row["descripcion"],
                    "cuenta": row["cuenta"],
                    "importe_fmt": formato_euros(float(row["importe"])),
                })
            ui.table(columns=columns, rows=rows, pagination=8).classes("w-full compact-table")

        render_detail("Gastos", gastos)
        render_detail("Ingresos", ingresos)
        ui.button("Cerrar", on_click=dialog.close).classes("self-end")
    dialog.open()
