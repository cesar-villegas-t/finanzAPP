from datetime import date

from nicegui import app, ui

from db.queries import (
    cargar_catalogo,
    consultar_movimientos,
    existe_transaccion,
    insertar_transaccion,
    insertar_transacciones_masivas,
    insertar_traspaso,
    opciones_filtro_movimientos,
    opciones_recientes_movimientos,
    resumen_movimientos,
    ultimo_traspaso_entre_cuentas_usuario,
)
from services.bulk_transactions import BulkImportError, EXPECTED_HEADER, parse_bulk_transactions_txt
from ui.components import (
    actualizar_color_importe,
    color_por_tipo,
    euro_label,
    formato_euros,
    formato_euros_sin_signo,
    open_duplicate_dialog,
    open_edit_transaction_dialog,
    quasar_dark_props,
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


def render_ingresos_gastos(refresh, usuario, is_dark=False):
    ui.label("Registro de Transacciones").classes("page-title")
    form_mode = {"value": "operacion"}
    batch_size = 50
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
        return opciones_filtro_movimientos(usuario, columna)

    def filtros_predeterminados():
        return (
            filtros["tipos"] == TIPOS_MOVIMIENTO
            and not filtros["cuentas"]
            and not filtros["sectores"]
            and filtros["orden"] == "Fecha"
            and filtros["direccion"] == "Descendente"
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
                ).props(
                    quasar_dark_props("outlined dense", is_dark)
                ).classes("flex-1 dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                orden_select = ui.select(
                    list(ORDEN_MOVIMIENTOS),
                    label="Ordenar por",
                    value=filtros["orden"],
                ).props(
                    quasar_dark_props("outlined dense", is_dark)
                ).classes("flex-1 dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                direccion_select = ui.select(
                    ["Descendente", "Ascendente"],
                    label="Dirección",
                    value=filtros["direccion"],
                ).props(
                    quasar_dark_props("outlined dense", is_dark)
                ).classes("flex-1 dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")

            with ui.row().classes("w-full gap-3 items-start"):
                cuentas_select = ui.select(
                    cuentas,
                    label="Cuentas",
                    value=filtros["cuentas"].copy(),
                    multiple=True,
                ).props(
                    quasar_dark_props("outlined dense", is_dark)
                ).classes("flex-1 dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")
                sectores_select = ui.select(
                    sectores,
                    label="Sectores",
                    value=filtros["sectores"].copy(),
                    multiple=True,
                ).props(
                    quasar_dark_props("outlined dense", is_dark)
                ).classes("flex-1 dark:bg-slate-900 dark:text-slate-100 dark:border-slate-700")

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

    with ui.card().classes("form-card max-w-xl mx-auto"):
        @ui.refreshable
        def render_form():
            opciones_cuenta = opciones_recientes_movimientos(
                usuario,
                "cuenta",
                cargar_catalogo("cuentas"),
                "Otra",
            )
            opciones_sector = opciones_recientes_movimientos(
                usuario,
                "sector",
                cargar_catalogo("sectores"),
                "Otro",
                excluir_tipos=["Traspaso"],
            )
            ultimo_form = ultima_operacion_form()

            def actualizar_select(select, opciones):
                valor_actual = select.value
                select.options = opciones
                if valor_actual not in opciones:
                    select.value = valor_preferido(opciones, valor_actual)
                select.update()

            def set_form_mode(mode):
                if mode not in {"operacion", "traspaso"} or mode == form_mode["value"]:
                    return
                form_mode["value"] = mode
                render_form.refresh()

            def style_entry_field(field, save_function, width_class="w-full"):
                return field.props(quasar_dark_props("outlined dense color=blue-8", is_dark)).classes(
                    f"{width_class} transaction-entry-field rounded-xl bg-slate-100 dark:bg-slate-900 "
                    "dark:text-slate-100 dark:border-slate-700 focus:bg-white dark:focus:bg-slate-900"
                ).on("keydown.enter", lambda _: save_function())

            def reveal_placeholder_on_focus(field, placeholder):
                field.on("focus", lambda _: field.props(f'placeholder="{placeholder}"'))
                field.on("blur", lambda _: field.props(remove="placeholder"))
                return field

            def style_hero_amount(field, save_function, signed=False):
                classes = (
                    "w-full max-w-md transaction-hero-amount bg-transparent dark:bg-transparent "
                    "border-none dark:text-slate-100 dark:border-transparent"
                )
                if signed:
                    classes = f"{classes} signed-amount-input"
                return field.props(
                    quasar_dark_props(
                        'borderless input-class="text-4xl font-bold text-right text-slate-900 dark:text-slate-100"',
                        is_dark,
                    )
                ).classes(classes).on("keydown.enter", lambda _: save_function())

            with ui.row().classes("w-full items-center justify-center relative"):
                with ui.tabs(value=form_mode["value"]).classes(
                    "asset-chart-tabs transaction-mode-tabs bg-[#F8FAFC] dark:bg-slate-900 rounded-full p-1 w-full max-w-sm"
                ).props('dense no-caps active-color="dark" indicator-color="transparent"') as mode_tabs:
                    ui.tab("operacion", label="Operación")
                    ui.tab("traspaso", label="Traspaso")
                mode_tabs.on("update:model-value", lambda event: set_form_mode(event.args))
                if form_mode["value"] == "operacion":
                    with ui.button(
                        icon="upload_file",
                        on_click=lambda: open_bulk_import_dialog(refresh, usuario),
                    ).props("flat round dense").classes(
                        "absolute right-0 top-1/2 -translate-y-1/2 text-slate-500 dark:text-slate-400"
                    ):
                        ui.tooltip("Importar registros desde .txt")

            if form_mode["value"] == "traspaso":
                ultima_cuenta_origen, ultima_cuenta_destino = ultimo_traspaso_entre_cuentas_usuario(usuario)
                cuenta_origen_default = (
                    ultima_cuenta_origen if ultima_cuenta_origen in opciones_cuenta else opciones_cuenta[0]
                )
                cuenta_destino_default = (
                    ultima_cuenta_destino if ultima_cuenta_destino in opciones_cuenta else opciones_cuenta[0]
                )

                with ui.column().classes("w-full items-center gap-1 py-4"):
                    ui.label("Importe (€)").classes("text-xs uppercase font-bold text-slate-400 tracking-wider")
                    importe_input = ui.number(value=None, min=0, step=1, suffix="€")
                    style_hero_amount(importe_input, lambda: save_transfer())

                with ui.column().classes("w-full bg-slate-50 dark:bg-slate-900 rounded-2xl p-4 space-y-3 gap-0"):
                    descripcion_input = ui.input(
                        "Descripción",
                    )
                    reveal_placeholder_on_focus(descripcion_input, "Ej: traspaso mensual")
                    style_entry_field(descripcion_input, lambda: save_transfer())

                    with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-3"):
                        fecha_input = ui.input("Fecha", value=date.today().isoformat()).props(
                            "type=date prepend-icon=calendar_month"
                        )
                        style_entry_field(fecha_input, lambda: save_transfer())
                        with ui.column().classes("w-full gap-2"):
                            cuenta_origen_select = ui.select(
                                opciones_cuenta,
                                label="Cuenta",
                                value=cuenta_origen_default,
                            )
                            style_entry_field(cuenta_origen_select, lambda: save_transfer())
                            nueva_cuenta_origen = ui.input("Nueva cuenta origen")
                            style_entry_field(nueva_cuenta_origen, lambda: save_transfer())

                    with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-3"):
                        with ui.column().classes("w-full gap-2"):
                            cuenta_destino_select = ui.select(
                                opciones_cuenta,
                                label="Cuenta destino",
                                value=cuenta_destino_default,
                            )
                            style_entry_field(cuenta_destino_select, lambda: save_transfer())
                            nueva_cuenta_destino = ui.input("Nueva cuenta destino")
                            style_entry_field(nueva_cuenta_destino, lambda: save_transfer())

                nueva_cuenta_origen.set_visibility(False)
                nueva_cuenta_destino.set_visibility(False)
                cuenta_origen_select.on_value_change(
                    lambda e: nueva_cuenta_origen.set_visibility(e.value == "Otra")
                )
                cuenta_destino_select.on_value_change(
                    lambda e: nueva_cuenta_destino.set_visibility(e.value == "Otra")
                )

                def refresh_transfer_account_options():
                    nuevas_opciones = opciones_recientes_movimientos(
                        usuario,
                        "cuenta",
                        cargar_catalogo("cuentas"),
                        "Otra",
                    )
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
                    refresh_view(refresh, f"Traspaso de {formato_euros_sin_signo(importe)} registrado correctamente.")

                ui.button("Registrar traspaso", icon="swap_horiz", on_click=save_transfer).props(
                    "unelevated no-caps size=lg"
                ).classes(
                    "w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl py-2.5 text-base"
                )
                return

            with ui.column().classes("w-full items-center gap-1 py-4"):
                ui.label("Importe (€)").classes("text-xs uppercase font-bold text-slate-400 tracking-wider")
                importe_input = ui.number(value=None, step=1, suffix="€")
                style_hero_amount(importe_input, lambda: save_transaction(), signed=True)
                importe_input.on_value_change(lambda e: actualizar_color_importe(importe_input, e.value))

            with ui.column().classes("w-full bg-slate-50 dark:bg-slate-900 rounded-2xl p-4 space-y-3 gap-0"):
                descripcion_input = ui.input(
                    "Descripción",
                )
                reveal_placeholder_on_focus(descripcion_input, "Ej: compra supermercado")
                style_entry_field(descripcion_input, lambda: save_transaction())

                with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-3"):
                    fecha_input = ui.input(
                        "Fecha",
                        value=ultimo_form.get("fecha") or date.today().isoformat(),
                    ).props("type=date prepend-icon=calendar_month")
                    style_entry_field(fecha_input, lambda: save_transaction())
                    with ui.column().classes("w-full gap-2"):
                        cuenta_select = ui.select(
                            opciones_cuenta,
                            label="Cuenta",
                            value=valor_preferido(opciones_cuenta, ultimo_form.get("cuenta")),
                        )
                        style_entry_field(cuenta_select, lambda: save_transaction())
                        nueva_cuenta = ui.input("Nueva cuenta")
                        style_entry_field(nueva_cuenta, lambda: save_transaction())

                with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-3"):
                    with ui.column().classes("w-full gap-2"):
                        sector_select = ui.select(
                            opciones_sector,
                            label="Sector",
                            value=valor_preferido(opciones_sector, ultimo_form.get("sector")),
                        )
                        style_entry_field(sector_select, lambda: save_transaction())
                        nuevo_sector = ui.input("Nuevo sector")
                        style_entry_field(nuevo_sector, lambda: save_transaction())
            nueva_cuenta.set_visibility(False)
            nuevo_sector.set_visibility(False)
            cuenta_select.on_value_change(lambda e: nueva_cuenta.set_visibility(e.value == "Otra"))
            sector_select.on_value_change(lambda e: nuevo_sector.set_visibility(e.value == "Otro"))

            def refresh_account_options():
                nuevas_opciones = opciones_recientes_movimientos(
                    usuario,
                    "cuenta",
                    cargar_catalogo("cuentas"),
                    "Otra",
                )
                actualizar_select(cuenta_select, nuevas_opciones)
                nueva_cuenta.set_visibility(cuenta_select.value == "Otra")

            def refresh_sector_options():
                nuevas_opciones = opciones_recientes_movimientos(
                    usuario,
                    "sector",
                    cargar_catalogo("sectores"),
                    "Otro",
                    excluir_tipos=["Traspaso"],
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
                refresh_view(refresh, f"{tipo} de {formato_euros_sin_signo(abs(importe))} registrado correctamente.")

            ui.button("Registrar operación", icon="add", on_click=save_transaction).props(
                "unelevated no-caps size=lg"
            ).classes("w-full bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl py-2.5 text-base")

        render_form()

    @ui.refreshable
    def render_movements():
        state = {
            "offset": 0,
            "loading": False,
            "has_more": True,
            "rows_container": None,
            "loading_label": None,
        }
        total_count, total_amount = resumen_movimientos(usuario, filtros)

        def render_row(row):
            with ui.element("div").classes("table-row transactions-table"):
                ui.label(str(row["fecha"]))
                ui.label(row["tipo"]).classes(f"font-semibold {color_por_tipo(row['tipo'])}")
                ui.label(row["descripcion"] or "")
                ui.label(row["cuenta"])
                ui.label(row["sector"])
                euro_label(float(row["importe"]))
                ui.button(
                    icon="edit",
                    on_click=lambda row=row: open_edit_transaction_dialog(row, refresh, usuario),
                ).props("flat dense")

        def append_movements():
            if state["loading"] or not state["has_more"]:
                return
            state["loading"] = True
            if state["loading_label"] is not None:
                state["loading_label"].set_visibility(True)
            movimientos = consultar_movimientos(
                usuario,
                filtros,
                limit=batch_size,
                offset=state["offset"],
            )
            if state["rows_container"] is not None:
                with state["rows_container"]:
                    for _, row in movimientos.iterrows():
                        render_row(row)
            loaded_count = len(movimientos)
            state["offset"] += loaded_count
            state["has_more"] = loaded_count == batch_size and state["offset"] < total_count
            if state["loading_label"] is not None:
                state["loading_label"].set_visibility(False)
            state["loading"] = False

        def handle_scroll(event):
            data = event.args or {}
            if not isinstance(data, dict):
                return
            scroll_top = float(data.get("scrollTop") or 0)
            client_height = float(data.get("clientHeight") or 0)
            scroll_height = float(data.get("scrollHeight") or 0)
            if scroll_top + client_height >= scroll_height - 160:
                append_movements()

        with ui.row().classes("w-full items-center justify-between mt-6"):
            ui.label("Movimientos").classes("section-title")
            ui.button(
                "Filtros",
                icon="filter_alt",
                on_click=lambda: open_filters_dialog(render_movements),
            ).props("outline dense")
        ui.label(resumen_filtros()).classes("text-sm text-gray-500")

        if total_count == 0 and filtros_predeterminados():
            ui.label("Aún no hay movimientos.").classes("text-gray-500")
            return

        if total_count == 0:
            ui.label("No hay movimientos que coincidan con los filtros.").classes("text-gray-500")
            return

        ui.label(
            f"{total_count} movimientos - Total {formato_euros(total_amount)}"
        ).classes("text-sm text-gray-500")

        with ui.card().classes("table-card"):
            with ui.element("div").classes("table-header transactions-table"):
                for label in ["Fecha", "Tipo", "Descripción", "Cuenta", "Sector", "Importe", ""]:
                    ui.label(label).classes("font-semibold")
            rows_container = ui.element("div").classes("movements-scroll")
            rows_container.on(
                "scroll",
                handle_scroll,
                throttle=0.3,
                leading_events=False,
                trailing_events=True,
                js_handler="""(event) => emit({
                    scrollTop: event.target.scrollTop,
                    clientHeight: event.target.clientHeight,
                    scrollHeight: event.target.scrollHeight
                })""",
            )
            state["rows_container"] = rows_container
            state["loading_label"] = ui.label("Cargando más movimientos...").classes(
                "movement-loading-label text-sm text-gray-500"
            )
            state["loading_label"].set_visibility(False)
            append_movements()

    render_movements()
    imported_count = app.storage.user.pop("bulk_import_success_count", None)
    if imported_count is not None:
        ui.timer(0.1, lambda: open_bulk_import_success_dialog(imported_count), once=True)
