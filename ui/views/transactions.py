from datetime import date

from nicegui import app, ui

from db.queries import (
    cargar_catalogo,
    cargar_datos,
    existe_transaccion,
    insertar_transaccion,
    insertar_transacciones_masivas,
    insertar_traspaso,
)
from services.bulk_transactions import BulkImportError, EXPECTED_HEADER, parse_bulk_transactions_txt
from services.analytics import opciones_por_uso_reciente, ultimo_traspaso_entre_cuentas
from ui.components import (
    actualizar_color_importe,
    color_por_tipo,
    euro_label,
    formato_euros,
    open_catalog_editor_dialog,
    open_duplicate_dialog,
    open_edit_transaction_dialog,
    refresh_view,
)


TIPOS_MOVIMIENTO = ["Ingreso", "Gasto", "Traspaso"]
LAST_TRANSACTION_FORM_KEY = "last_manual_transaction_form"
ORDEN_MOVIMIENTOS = {
    "Fecha": "fecha",
    "Fecha de registro": "fecha_registro",
    "Importe": "importe",
}


def open_bulk_import_error_dialog(message):
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        ui.label("No se pudo importar el archivo").classes("text-xl font-semibold")
        ui.label(message).classes("text-sm text-gray-700")
        ui.button("Entendido", on_click=dialog.close).classes("self-end")
    dialog.open()


def open_bulk_import_success_dialog(imported_count):
    with ui.dialog() as dialog, ui.card().classes("dialog-card"):
        ui.label("Importacion completada").classes("text-xl font-semibold")
        ui.label(f"Se han ingestado {imported_count} registros correctamente.").classes("text-sm text-gray-700")
        ui.button("Cerrar", icon="check", on_click=dialog.close, color="primary").classes("self-end")
    dialog.open()


def open_bulk_import_dialog(refresh, usuario):
    with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
        ui.label("Importar operaciones desde .txt").classes("text-2xl font-semibold")
        ui.label(
            "El archivo debe usar separador |, mantener la cabecera exacta y contener una operacion por linea."
        ).classes("text-sm text-gray-600")

        with ui.card().classes("w-full"):
            ui.label("Formato requerido").classes("text-base font-semibold")
            ui.label(EXPECTED_HEADER).classes("text-sm font-mono text-gray-700")
            ui.label("2026-07-27|Ingreso|Parte de Solans del viaje a Malaga|BBVA|Viajes|117.0").classes(
                "text-sm font-mono text-gray-700"
            )
            ui.label("2026-07-27|Gasto|Fulitu con Hector y Chacon|BBVA|Tomar algo|-4.65").classes(
                "text-sm font-mono text-gray-700"
            )
            ui.label("2026-07-28|Traspaso|Traspaso mensual - salida|Trade Republic|Traspaso entre cuentas|-180.0").classes(
                "text-sm font-mono text-gray-700"
            )
            ui.label("2026-07-28|Traspaso|Traspaso mensual - entrada|MyInvestor|Traspaso entre cuentas|180.0").classes(
                "text-sm font-mono text-gray-700"
            )

        with ui.element("div").classes("text-sm text-gray-600"):
            ui.label("Validaciones antes de insertar:")
            ui.label("- Fechas reales con formato yyyy-mm-dd.")
            ui.label("- Tipo exacto: Ingreso, Gasto o Traspaso.")
            ui.label("- Cuenta y sector ya existentes en la configuracion.")
            ui.label("- Ingresos positivos y gastos negativos.")
            ui.label("- Cada traspaso debe usar el sector Traspaso entre cuentas.")
            ui.label("- Cada traspaso debe tener entrada y salida con signos opuestos.")

        def handle_upload(event):
            if not (event.name or "").lower().endswith(".txt"):
                event.sender.reset()
                open_bulk_import_error_dialog("El archivo debe tener extension .txt.")
                return
            try:
                content = event.content.read()
                registros = parse_bulk_transactions_txt(
                    content,
                    cargar_catalogo("cuentas"),
                    cargar_catalogo("sectores"),
                )
                imported_count = insertar_transacciones_masivas(registros, usuario)
            except BulkImportError as exc:
                event.sender.reset()
                open_bulk_import_error_dialog(str(exc))
                return
            dialog.close()
            app.storage.user["bulk_import_success_count"] = imported_count
            refresh()

        uploader = ui.upload(
            label="Seleccionar archivo .txt",
            auto_upload=True,
            max_file_size=1_000_000,
            on_upload=handle_upload,
            on_rejected=lambda _: open_bulk_import_error_dialog(
                "El archivo supera el limite permitido o no cumple el tipo esperado."
            ),
        ).classes("w-full")
        uploader.props('accept=".txt,text/plain"')

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Cancelar", on_click=dialog.close, color="grey")
    dialog.open()


def render_ingresos_gastos(refresh, usuario):
    df_tx = cargar_datos("transacciones", usuario)
    if "fecha_registro" not in df_tx.columns:
        df_tx["fecha_registro"] = df_tx["fecha"] if "fecha" in df_tx.columns else None
    ui.label("Registro de Transacciones").classes("page-title")
    form_mode = {"value": "operacion"}
    filtros = {
        "tipos": TIPOS_MOVIMIENTO.copy(),
        "cuentas": [],
        "sectores": [],
        "orden": "Fecha",
        "direccion": "Descendente",
    }

    def ultima_operacion_form():
        data = app.storage.user.get(LAST_TRANSACTION_FORM_KEY)
        return data if isinstance(data, dict) else {}

    def valor_preferido(opciones, valor):
        return valor if valor in opciones else (opciones[0] if opciones else None)

    def guardar_ultima_operacion_form(data):
        app.storage.user[LAST_TRANSACTION_FORM_KEY] = {
            "fecha": data["fecha"],
            "cuenta": data["cuenta"],
            "sector": data["sector"],
        }

    def opciones_filtro(columna):
        if df_tx.empty or columna not in df_tx.columns:
            return []
        valores = df_tx[columna].dropna().astype(str).str.strip()
        return sorted({valor for valor in valores if valor}, key=str.lower)

    def aplicar_filtros_movimientos():
        movimientos = df_tx.copy()
        if movimientos.empty:
            return movimientos

        if "fecha_registro" not in movimientos.columns:
            movimientos["fecha_registro"] = movimientos["fecha"]
        movimientos["fecha_registro"] = movimientos["fecha_registro"].fillna(movimientos["fecha"])

        if filtros["tipos"]:
            movimientos = movimientos[movimientos["tipo"].isin(filtros["tipos"])]
        if filtros["cuentas"]:
            movimientos = movimientos[movimientos["cuenta"].isin(filtros["cuentas"])]
        if filtros["sectores"]:
            movimientos = movimientos[movimientos["sector"].isin(filtros["sectores"])]

        columna_orden = ORDEN_MOVIMIENTOS[filtros["orden"]]
        ascendente = filtros["direccion"] == "Ascendente"
        if columna_orden in {"fecha", "fecha_registro"}:
            movimientos = movimientos.assign(
                _orden_fecha=movimientos[columna_orden].fillna(movimientos["fecha"])
            )
            return movimientos.sort_values(
                ["_orden_fecha", "id"],
                ascending=[ascendente, ascendente],
            ).drop(columns=["_orden_fecha"])

        return movimientos.sort_values(
            [columna_orden, "id"],
            ascending=[ascendente, ascendente],
        )

    def resumen_filtros():
        partes = []
        if filtros["tipos"] != TIPOS_MOVIMIENTO:
            partes.append(f"{len(filtros['tipos'])} tipos")
        if filtros["cuentas"]:
            partes.append(f"{len(filtros['cuentas'])} cuentas")
        if filtros["sectores"]:
            partes.append(f"{len(filtros['sectores'])} sectores")
        partes.append(f"{filtros['orden']} {filtros['direccion'].lower()}")
        return " - ".join(partes)

    def open_accounts_editor(on_close=None):
        open_catalog_editor_dialog(
            titulo="Editar cuentas",
            tabla="cuentas",
            columna_uso="cuenta",
            input_label="Nueva cuenta",
            add_button_label="Añadir cuenta",
            usuario=usuario,
            on_close=on_close,
        )

    def open_filters_dialog(render_movements):
        cuentas = opciones_filtro("cuenta")
        sectores = opciones_filtro("sector")

        with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
            ui.label("Filtros de movimientos").classes("text-xl font-semibold")

            with ui.row().classes("w-full gap-3 items-start"):
                tipos_select = ui.select(
                    TIPOS_MOVIMIENTO,
                    label="Tipo",
                    value=filtros["tipos"].copy(),
                    multiple=True,
                ).classes("flex-1")
                orden_select = ui.select(
                    list(ORDEN_MOVIMIENTOS),
                    label="Ordenar por",
                    value=filtros["orden"],
                ).classes("flex-1")
                direccion_select = ui.select(
                    ["Descendente", "Ascendente"],
                    label="Dirección",
                    value=filtros["direccion"],
                ).classes("flex-1")

            with ui.row().classes("w-full gap-3 items-start"):
                cuentas_select = ui.select(
                    cuentas,
                    label="Cuentas",
                    value=filtros["cuentas"].copy(),
                    multiple=True,
                ).classes("flex-1")
                sectores_select = ui.select(
                    sectores,
                    label="Sectores",
                    value=filtros["sectores"].copy(),
                    multiple=True,
                ).classes("flex-1")

            def reset_filters():
                tipos_select.value = TIPOS_MOVIMIENTO.copy()
                cuentas_select.value = []
                sectores_select.value = []
                orden_select.value = "Fecha"
                direccion_select.value = "Descendente"

            def apply_filters():
                if not tipos_select.value:
                    ui.notify("Selecciona al menos un tipo.", color="warning")
                    return
                filtros["tipos"] = list(tipos_select.value or [])
                filtros["cuentas"] = list(cuentas_select.value or [])
                filtros["sectores"] = list(sectores_select.value or [])
                filtros["orden"] = orden_select.value or "Fecha"
                filtros["direccion"] = direccion_select.value or "Descendente"
                dialog.close()
                render_movements.refresh()

            with ui.row().classes("w-full justify-between gap-2"):
                ui.button("Restablecer", icon="restart_alt", on_click=reset_filters).props("outline")
                with ui.row().classes("gap-2"):
                    ui.button("Cancelar", on_click=dialog.close, color="grey").props("outline")
                    ui.button("Aplicar", icon="check", on_click=apply_filters, color="primary")

        dialog.open()

    with ui.card().classes("form-card"):
        @ui.refreshable
        def render_form():
            opciones_cuenta = opciones_por_uso_reciente(df_tx, "cuenta", cargar_catalogo("cuentas"), "Otra")
            df_tx_operaciones = df_tx[df_tx["tipo"] != "Traspaso"] if not df_tx.empty else df_tx
            opciones_sector = opciones_por_uso_reciente(df_tx_operaciones, "sector", cargar_catalogo("sectores"), "Otro")
            ultimo_form = ultima_operacion_form()

            def actualizar_select(select, opciones):
                valor_actual = select.value
                select.options = opciones
                if valor_actual not in opciones:
                    select.value = valor_preferido(opciones, valor_actual)
                select.update()

            if form_mode["value"] == "traspaso":
                ui.label("Traspaso entre cuentas").classes("section-title")
                fecha_input = ui.input("Fecha", value=date.today().isoformat()).props("type=date").classes("w-48")
                ultima_cuenta_origen, ultima_cuenta_destino = ultimo_traspaso_entre_cuentas(df_tx)
                cuenta_origen_default = (
                    ultima_cuenta_origen if ultima_cuenta_origen in opciones_cuenta else opciones_cuenta[0]
                )
                cuenta_destino_default = (
                    ultima_cuenta_destino if ultima_cuenta_destino in opciones_cuenta else opciones_cuenta[0]
                )
                with ui.row().classes("w-full gap-3"):
                    importe_input = ui.number("Importe (€)", value=None, min=0, step=1).classes("flex-1")
                    descripcion_input = ui.input("Descripción", placeholder="Ej: traspaso mensual").classes("flex-1")

                with ui.row().classes("w-full gap-3 items-start"):
                    with ui.column().classes("flex-1 gap-2"):
                        cuenta_origen_select = ui.select(
                            opciones_cuenta,
                            label="Cuenta origen",
                            value=cuenta_origen_default,
                        ).classes("w-full")
                        nueva_cuenta_origen = ui.input("Nueva cuenta origen").classes("w-full")
                    with ui.column().classes("flex-1 gap-2"):
                        with ui.row().classes("w-full gap-2 items-center"):
                            cuenta_destino_select = ui.select(
                                opciones_cuenta,
                                label="Cuenta destino",
                                value=cuenta_destino_default,
                            ).classes("flex-1")
                            ui.button(
                                "Editar cuentas",
                                icon="settings",
                                on_click=lambda: open_accounts_editor(refresh_transfer_account_options),
                            ).props("outline dense").classes("text-xs")
                        nueva_cuenta_destino = ui.input("Nueva cuenta destino").classes("w-full")

                nueva_cuenta_origen.set_visibility(False)
                nueva_cuenta_destino.set_visibility(False)
                cuenta_origen_select.on_value_change(
                    lambda e: nueva_cuenta_origen.set_visibility(e.value == "Otra")
                )
                cuenta_destino_select.on_value_change(
                    lambda e: nueva_cuenta_destino.set_visibility(e.value == "Otra")
                )

                def refresh_transfer_account_options():
                    nuevas_opciones = opciones_por_uso_reciente(df_tx, "cuenta", cargar_catalogo("cuentas"), "Otra")
                    actualizar_select(cuenta_origen_select, nuevas_opciones)
                    actualizar_select(cuenta_destino_select, nuevas_opciones)
                    nueva_cuenta_origen.set_visibility(cuenta_origen_select.value == "Otra")
                    nueva_cuenta_destino.set_visibility(cuenta_destino_select.value == "Otra")

                def save_transfer():
                    importe = float(importe_input.value or 0)
                    if importe <= 0:
                        ui.notify("El importe del traspaso debe ser positivo.", color="warning")
                        return
                    cuenta_origen = (
                        (nueva_cuenta_origen.value or "").strip()
                        if cuenta_origen_select.value == "Otra"
                        else cuenta_origen_select.value
                    )
                    cuenta_destino = (
                        (nueva_cuenta_destino.value or "").strip()
                        if cuenta_destino_select.value == "Otra"
                        else cuenta_destino_select.value
                    )
                    if not cuenta_origen or not cuenta_destino:
                        ui.notify("Indica la cuenta origen y la cuenta destino.", color="warning")
                        return
                    if cuenta_origen == cuenta_destino:
                        ui.notify("La cuenta origen y destino deben ser distintas.", color="warning")
                        return
                    insertar_traspaso(
                        fecha_input.value,
                        descripcion_input.value or "",
                        cuenta_origen,
                        cuenta_destino,
                        importe,
                        usuario,
                    )
                    refresh_view(refresh, f"Traspaso de {importe:.2f}€ registrado correctamente.")

                def show_operation_form():
                    form_mode["value"] = "operacion"
                    render_form.refresh()

                with ui.row().classes("self-start gap-2"):
                    ui.button("Registrar traspaso", icon="swap_horiz", on_click=save_transfer)
                    ui.button(
                        "Añadir nueva operación",
                        icon="receipt_long",
                        on_click=show_operation_form,
                    ).props("outline")
                return

            with ui.row().classes("items-center gap-2"):
                ui.label("Añadir nueva operación").classes("section-title")
                with ui.button(
                    icon="upload_file",
                    on_click=lambda: open_bulk_import_dialog(refresh, usuario),
                ).props("outline round dense"):
                    ui.tooltip("Importar registros desde .txt")
            fecha_input = ui.input(
                "Fecha",
                value=ultimo_form.get("fecha") or date.today().isoformat(),
            ).props("type=date").classes("w-48")
            with ui.row().classes("w-full gap-3"):
                importe_input = ui.number("Importe (€)", value=None, step=1).classes(
                    "flex-1 signed-amount-input"
                )
                importe_input.on_value_change(lambda e: actualizar_color_importe(importe_input, e.value))
                descripcion_input = ui.input("Descripción", placeholder="Ej: compra supermercado").classes("flex-1")

            with ui.row().classes("w-full gap-3 items-start"):
                with ui.column().classes("flex-1 gap-2"):
                    with ui.row().classes("w-full gap-2 items-center"):
                        cuenta_select = ui.select(
                            opciones_cuenta,
                            label="Cuenta",
                            value=valor_preferido(opciones_cuenta, ultimo_form.get("cuenta")),
                        ).classes("flex-1")
                        ui.button(
                            "Editar cuentas",
                            icon="settings",
                            on_click=lambda: open_accounts_editor(refresh_account_options),
                        ).props("outline dense").classes("text-xs")
                    nueva_cuenta = ui.input("Nueva cuenta").classes("w-full")
                with ui.column().classes("flex-1 gap-2"):
                    with ui.row().classes("w-full gap-2 items-center"):
                        sector_select = ui.select(
                            opciones_sector,
                            label="Sector",
                            value=valor_preferido(opciones_sector, ultimo_form.get("sector")),
                        ).classes("flex-1")
                        ui.button(
                            "Editar sectores",
                            icon="settings",
                            on_click=lambda: open_catalog_editor_dialog(
                                titulo="Editar sectores",
                                tabla="sectores",
                                columna_uso="sector",
                                input_label="Nuevo sector",
                                add_button_label="Añadir sector",
                                usuario=usuario,
                                on_close=refresh_sector_options,
                            ),
                        ).props("outline dense").classes("text-xs")
                    nuevo_sector = ui.input("Nuevo sector").classes("w-full")
            nueva_cuenta.set_visibility(False)
            nuevo_sector.set_visibility(False)
            cuenta_select.on_value_change(lambda e: nueva_cuenta.set_visibility(e.value == "Otra"))
            sector_select.on_value_change(lambda e: nuevo_sector.set_visibility(e.value == "Otro"))

            def refresh_account_options():
                nuevas_opciones = opciones_por_uso_reciente(df_tx, "cuenta", cargar_catalogo("cuentas"), "Otra")
                actualizar_select(cuenta_select, nuevas_opciones)
                nueva_cuenta.set_visibility(cuenta_select.value == "Otra")

            def refresh_sector_options():
                nuevas_opciones = opciones_por_uso_reciente(
                    df_tx_operaciones,
                    "sector",
                    cargar_catalogo("sectores"),
                    "Otro",
                )
                actualizar_select(sector_select, nuevas_opciones)
                nuevo_sector.set_visibility(sector_select.value == "Otro")

            def save_transaction():
                importe = float(importe_input.value or 0)
                if importe == 0:
                    ui.notify("El importe no puede ser 0.", color="warning")
                    return
                cuenta = (nueva_cuenta.value or "").strip() if cuenta_select.value == "Otra" else cuenta_select.value
                sector = (nuevo_sector.value or "").strip() if sector_select.value == "Otro" else sector_select.value
                if not cuenta or not sector:
                    ui.notify("Indica la cuenta o sector nuevo.", color="warning")
                    return
                tipo = "Ingreso" if importe > 0 else "Gasto"
                data = {
                    "fecha": fecha_input.value,
                    "tipo": tipo,
                    "descripcion": descripcion_input.value or "",
                    "cuenta": cuenta,
                    "sector": sector,
                    "importe": importe,
                }
                if existe_transaccion(**data, usuario=usuario):
                    open_duplicate_dialog(
                        data,
                        refresh,
                        usuario,
                        on_confirm=lambda data=data: guardar_ultima_operacion_form(data),
                    )
                    return
                insertar_transaccion(**data, usuario=usuario)
                guardar_ultima_operacion_form(data)
                refresh_view(refresh, f"{tipo} de {abs(importe):.2f}€ registrado correctamente.")

            def show_transfer_form():
                form_mode["value"] = "traspaso"
                render_form.refresh()

            with ui.row().classes("self-start gap-2"):
                ui.button("Registrar Operación", icon="add", on_click=save_transaction)
                ui.button(
                    "Traspaso entre cuentas",
                    icon="swap_horiz",
                    on_click=show_transfer_form,
                ).props("outline")

        render_form()

    @ui.refreshable
    def render_movements():
        with ui.row().classes("w-full items-center justify-between mt-6"):
            ui.label("Movimientos").classes("section-title")
            ui.button(
                "Filtros",
                icon="filter_alt",
                on_click=lambda: open_filters_dialog(render_movements),
            ).props("outline dense")
        ui.label(resumen_filtros()).classes("text-sm text-gray-500")

        if df_tx.empty:
            ui.label("Aún no hay movimientos.").classes("text-gray-500")
            return

        movimientos = aplicar_filtros_movimientos()
        if movimientos.empty:
            ui.label("No hay movimientos que coincidan con los filtros.").classes("text-gray-500")
            return

        total = float(movimientos["importe"].sum())
        ui.label(
            f"{len(movimientos)} movimientos - Total {formato_euros(total)}"
        ).classes("text-sm text-gray-500")

        with ui.card().classes("table-card"):
            with ui.element("div").classes("table-header transactions-table"):
                for label in ["Fecha", "Tipo", "Descripción", "Cuenta", "Sector", "Importe", ""]:
                    ui.label(label).classes("font-semibold")
            for _, row in movimientos.iterrows():
                with ui.element("div").classes("table-row transactions-table"):
                    ui.label(str(row["fecha"]))
                    ui.label(row["tipo"]).classes(f"font-semibold {color_por_tipo(row['tipo'])}")
                    ui.label(row["descripcion"] or "")
                    ui.label(row["cuenta"])
                    ui.label(row["sector"])
                    euro_label(float(row["importe"]))
                    ui.button(
                        "Editar",
                        icon="edit",
                        on_click=lambda row=row: open_edit_transaction_dialog(row, refresh, usuario),
                    ).props("dense")

    render_movements()
    imported_count = app.storage.user.pop("bulk_import_success_count", None)
    if imported_count is not None:
        ui.timer(0.1, lambda: open_bulk_import_success_dialog(imported_count), once=True)
