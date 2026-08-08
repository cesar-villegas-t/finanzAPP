from datetime import date

import pandas as pd
import plotly.express as px
from nicegui import ui

from db.queries import cargar_datos, cargar_preferencia_usuario, guardar_preferencia_usuario
from services.analytics import normalizar_sector, primer_dia_mes_anterior, resumen_gasto_por_sector
from ui.components import (
    color_por_signo,
    formato_euros,
    formato_euros_sin_signo,
    metric_card,
    open_sector_breakdown_dialog,
)


PREFERENCIA_FILTROS_ANALISIS = "analisis_gasto_filtros"
COLOR_POSITIVE = "#10B981"
COLOR_NEGATIVE = "#F43F5E"
CHART_COLORS = ["#3B82F6", "#06B6D4", "#8B5CF6", "#F97316", "#F43F5E"]


def _sectores_disponibles(df_tx):
    if df_tx.empty or "sector" not in df_tx.columns:
        return []
    sectores = [normalizar_sector(valor) for valor in df_tx["sector"].tolist()]
    return sorted({sector for sector in sectores if sector}, key=str.lower)


def _normalizar_fecha(valor, fallback):
    fecha = pd.to_datetime(valor, errors="coerce")
    return fallback if pd.isna(fecha) else fecha.date().isoformat()


def _filtros_por_defecto(df_tx):
    return {
        "fecha_inicio": primer_dia_mes_anterior().isoformat(),
        "fecha_fin": date.today().isoformat(),
        "sectores": _sectores_disponibles(df_tx),
    }


def _cargar_filtros_analisis(usuario, df_tx):
    sectores = _sectores_disponibles(df_tx)
    filtros = _filtros_por_defecto(df_tx)
    guardados = cargar_preferencia_usuario(PREFERENCIA_FILTROS_ANALISIS, usuario, {}) or {}

    filtros["fecha_inicio"] = _normalizar_fecha(
        guardados.get("fecha_inicio"),
        filtros["fecha_inicio"],
    )
    filtros["fecha_fin"] = _normalizar_fecha(
        guardados.get("fecha_fin"),
        filtros["fecha_fin"],
    )

    sectores_guardados = guardados.get("sectores")
    if isinstance(sectores_guardados, list):
        filtros["sectores"] = [sector for sector in sectores_guardados if sector in sectores]
        if not filtros["sectores"] and sectores:
            filtros["sectores"] = sectores
    return filtros


def render_analisis_gasto(usuario):
    df_tx = cargar_datos("transacciones", usuario)
    filtros = _cargar_filtros_analisis(usuario, df_tx)

    ui.label("Análisis de gasto").classes("page-title")

    def resumen_filtros():
        total_sectores = len(_sectores_disponibles(df_tx))
        sectores = filtros["sectores"]
        if not sectores:
            sector_texto = "0 sectores"
        elif len(sectores) == total_sectores:
            sector_texto = "Todos los sectores"
        else:
            sector_texto = f"{len(sectores)} sectores"
        return f"{filtros['fecha_inicio']} - {filtros['fecha_fin']} · {sector_texto}"

    def fechas_validas():
        fecha_inicio = pd.to_datetime(filtros["fecha_inicio"], errors="coerce")
        fecha_fin = pd.to_datetime(filtros["fecha_fin"], errors="coerce")
        if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
            return None, None
        fecha_inicio = fecha_inicio.date()
        fecha_fin = fecha_fin.date()
        if fecha_inicio > fecha_fin:
            return None, None
        return fecha_inicio, fecha_fin

    def open_filters_dialog(render_resultados):
        sectores = _sectores_disponibles(df_tx)

        with ui.dialog() as dialog, ui.card().classes("dialog-card wide-dialog"):
            ui.label("Filtros de análisis").classes("text-xl font-semibold")

            with ui.row().classes("w-full gap-3 items-start"):
                fecha_inicio_input = ui.input(
                    "Fecha de inicio",
                    value=filtros["fecha_inicio"],
                ).props("type=date").classes("flex-1")
                fecha_fin_input = ui.input(
                    "Fecha de fin",
                    value=filtros["fecha_fin"],
                ).props("type=date").classes("flex-1")

            ui.label("Sectores").classes("text-sm font-semibold text-gray-700")
            sector_checks = {}
            with ui.row().classes("w-full items-center justify-between gap-2"):
                selected_count = ui.label("").classes("text-sm text-gray-500")
                with ui.row().classes("gap-2"):
                    select_all_button = ui.button("Todos", icon="done_all").props("outline dense")
                    clear_button = ui.button("Ninguno", icon="remove_done").props("outline dense")

            with ui.element("div").classes("analysis-sector-grid"):
                for sector in sectores:
                    with ui.element("div").classes("analysis-sector-chip"):
                        checkbox = ui.checkbox(
                            sector,
                            value=sector in filtros["sectores"],
                        ).classes("analysis-sector-checkbox")
                        sector_checks[sector] = checkbox

            def selected_sectors():
                return [sector for sector, checkbox in sector_checks.items() if checkbox.value]

            def sync_sector_count():
                selected_count.set_text(f"{len(selected_sectors())} de {len(sectores)} seleccionados")

            def set_all_sectors(value):
                for checkbox in sector_checks.values():
                    checkbox.set_value(value)
                sync_sector_count()

            for checkbox in sector_checks.values():
                checkbox.on_value_change(lambda _: sync_sector_count())
            select_all_button.on("click", lambda _: set_all_sectors(True))
            clear_button.on("click", lambda _: set_all_sectors(False))
            sync_sector_count()

            def reset_filters():
                defaults = _filtros_por_defecto(df_tx)
                fecha_inicio_input.set_value(defaults["fecha_inicio"])
                fecha_fin_input.set_value(defaults["fecha_fin"])
                default_sectors = set(defaults["sectores"])
                for sector, checkbox in sector_checks.items():
                    checkbox.set_value(sector in default_sectors)
                sync_sector_count()

            def apply_filters():
                fecha_inicio = pd.to_datetime(fecha_inicio_input.value, errors="coerce")
                fecha_fin = pd.to_datetime(fecha_fin_input.value, errors="coerce")
                if pd.isna(fecha_inicio) or pd.isna(fecha_fin):
                    ui.notify("Selecciona fechas válidas.", color="warning")
                    return
                if fecha_inicio.date() > fecha_fin.date():
                    ui.notify("La fecha de inicio no puede ser posterior a la fecha de fin.", color="warning")
                    return
                sectores_seleccionados = selected_sectors()
                if not sectores_seleccionados:
                    ui.notify("Selecciona al menos un sector.", color="warning")
                    return

                filtros["fecha_inicio"] = fecha_inicio.date().isoformat()
                filtros["fecha_fin"] = fecha_fin.date().isoformat()
                filtros["sectores"] = sectores_seleccionados
                guardar_preferencia_usuario(PREFERENCIA_FILTROS_ANALISIS, filtros, usuario)
                dialog.close()
                render_resultados.refresh()

            with ui.row().classes("w-full justify-between gap-2"):
                ui.button("Restablecer", icon="restart_alt", on_click=reset_filters).props("outline")
                with ui.row().classes("gap-2"):
                    ui.button("Cancelar", on_click=dialog.close, color="grey").props("outline")
                    ui.button("Aplicar", icon="check", on_click=apply_filters, color="primary")

        dialog.open()

    @ui.refreshable
    def render_resultados():
        ui.button(
            "Filtros",
            icon="filter_alt",
            on_click=lambda: open_filters_dialog(render_resultados),
        ).props("outline dense")
        ui.label(resumen_filtros()).classes("text-sm text-gray-500")

        fecha_inicio, fecha_fin = fechas_validas()
        if fecha_inicio is None or fecha_fin is None:
            ui.label("Selecciona un rango de fechas válido.").classes("text-gray-500")
            return

        resumen = resumen_gasto_por_sector(
            df_tx,
            fecha_inicio,
            fecha_fin=fecha_fin,
            sectores=filtros["sectores"],
        )
        if resumen.empty:
            ui.label("No hay movimientos que coincidan con los filtros.").classes("text-gray-500")
            return

        with ui.row().classes("w-full gap-4"):
            metric_card("Gastos", formato_euros_sin_signo(resumen["Gastos"].sum()), "text-red-700")
            metric_card("Ingresos", formato_euros_sin_signo(resumen["Ingresos"].sum()), "text-green-700")
            metric_card("Balance", formato_euros(resumen["Balance"].sum()), color_por_signo(resumen["Balance"].sum()))

        ui.label("Resumen por sector").classes("section-title")
        with ui.card().classes("table-card"):
            with ui.element("div").classes("table-header sector-table"):
                for label in ["Sector", "Gastos", "Ingresos", "Balance", ""]:
                    ui.label(label).classes("font-semibold")
            for _, row in resumen.iterrows():
                with ui.element("div").classes("table-row sector-table"):
                    ui.label(row["Sector"])
                    ui.label(formato_euros_sin_signo(row["Gastos"])).classes("font-semibold text-red-700")
                    ui.label(formato_euros_sin_signo(row["Ingresos"])).classes("font-semibold text-green-700")
                    ui.label(formato_euros(row["Balance"])).classes(f"font-semibold {color_por_signo(row['Balance'])}")
                    ui.button(
                        "Desglose",
                        on_click=lambda row=row: open_sector_breakdown_dialog(
                            df_tx,
                            row["Sector"],
                            fecha_inicio,
                            fecha_fin,
                        ),
                    ).props("dense")

        ui.label("Desglose visual").classes("section-title")
        with ui.row().classes("w-full gap-4 items-stretch"):
            with ui.card().classes("chart-card"):
                resumen_graficos = resumen.copy()
                resumen_graficos["Resultado"] = resumen_graficos["Balance"].apply(
                    lambda v: "Positivo" if v >= 0 else "Negativo"
                )
                fig = px.bar(
                    resumen_graficos,
                    x="Sector",
                    y="Balance",
                    color="Resultado",
                    title="Balance por sector",
                    color_discrete_map={"Positivo": COLOR_POSITIVE, "Negativo": COLOR_NEGATIVE},
                )
                fig.update_yaxes(ticksuffix="€")
                fig.update_layout(legend_title_text="")
                ui.plotly(fig).classes("w-full")
            with ui.card().classes("chart-card"):
                perdidas = resumen[resumen["Balance"] < 0].copy()
                if perdidas.empty:
                    ui.label("No hay balances negativos en los sectores seleccionados.").classes("text-gray-500")
                else:
                    perdidas["Pérdida"] = perdidas["Balance"].abs()
                    fig = px.pie(
                        perdidas,
                        names="Sector",
                        values="Pérdida",
                        hole=0.45,
                        title="Reparto de pérdidas por sector",
                        color_discrete_sequence=CHART_COLORS,
                    )
                    ui.plotly(fig).classes("w-full")

    render_resultados()

