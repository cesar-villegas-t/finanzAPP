import pandas as pd
import plotly.express as px
from nicegui import ui

from db.queries import cargar_datos
from services.analytics import calcular_liquidez_por_fecha, calcular_patrimonio_total_por_fecha
from ui.components import color_por_signo, formato_euros_sin_signo, metric_card


def prepare_chart(fig, height=420):
    fig.update_layout(
        autosize=True,
        height=height,
        margin={"l": 24, "r": 24, "t": 48, "b": 24},
    )
    return fig


def render_saldo_global(usuario):
    df_tx = cargar_datos("transacciones", usuario)
    df_inv = cargar_datos("inversiones", usuario)
    saldo_efectivo = df_tx["importe"].sum() if not df_tx.empty else 0.0
    valor_inversiones = 0.0
    dinero_inicial_inversiones = 0.0
    df_inv_latest = pd.DataFrame()
    if not df_inv.empty:
        df_inv_latest = df_inv.sort_values(["fecha", "id"]).drop_duplicates("inversion", keep="last")
        df_inv_latest = df_inv_latest[df_inv_latest["valor_actual"] > 0]
        valor_inversiones = df_inv_latest["valor_actual"].sum()
        dinero_inicial_inversiones = df_inv_latest["dinero_inicial"].sum()
    balance_inversiones = valor_inversiones - dinero_inicial_inversiones
    balance_inversiones_pct = (
        balance_inversiones / dinero_inicial_inversiones * 100
        if dinero_inicial_inversiones
        else 0.0
    )
    patrimonio_total = saldo_efectivo + valor_inversiones

    ui.label("Resumen de Patrimonio Global").classes("page-title")
    with ui.row().classes("w-full gap-4"):
        metric_card("Patrimonio Total", formato_euros_sin_signo(patrimonio_total))
        metric_card("Liquidez (Cuentas)", formato_euros_sin_signo(saldo_efectivo))
        with ui.card().classes("metric-card"):
            ui.label("Valor Inversiones").classes("metric-label")
            with ui.row().classes("items-baseline gap-2"):
                ui.label(formato_euros_sin_signo(valor_inversiones)).classes("metric-value")
                ui.label(
                    f"{'+' if balance_inversiones_pct > 0 else ''}{balance_inversiones_pct:.2f}%"
                ).classes(f"text-sm font-semibold {color_por_signo(balance_inversiones_pct)}")

    with ui.row().classes("w-full gap-4 items-stretch"):
        with ui.card().classes("chart-card"):
            ui.label("Distribución de Liquidez por Cuenta").classes("section-title")
            if not df_tx.empty:
                distribucion = df_tx.groupby("cuenta")["importe"].sum().reset_index()
                distribucion = distribucion[distribucion["importe"] > 0]
                if not distribucion.empty:
                    fig = px.pie(distribucion, values="importe", names="cuenta", hole=0.4)
                    ui.plotly(prepare_chart(fig)).classes("plotly-chart")
                else:
                    ui.label("No hay saldo positivo en las cuentas.").classes("text-gray-500")
            else:
                ui.label("Aún no hay transacciones registradas.").classes("text-gray-500")

        with ui.card().classes("chart-card"):
            ui.label("Distribución de Inversiones").classes("section-title")
            if not df_inv_latest.empty:
                fig = px.pie(df_inv_latest, values="valor_actual", names="inversion", hole=0.4)
                ui.plotly(prepare_chart(fig)).classes("plotly-chart")
            else:
                ui.label("Aún no hay inversiones registradas.").classes("text-gray-500")

    with ui.row().classes("w-full gap-4 items-stretch"):
        with ui.card().classes("chart-card"):
            ui.label("Liquidez total por fecha").classes("section-title")
            liquidez = calcular_liquidez_por_fecha(df_tx)
            if not liquidez.empty:
                fig = px.line(liquidez, x="Fecha", y="Liquidez", markers=True)
                fig.update_yaxes(ticksuffix="€")
                ui.plotly(prepare_chart(fig)).classes("plotly-chart")
            else:
                ui.label("Aún no hay transacciones registradas.").classes("text-gray-500")
        with ui.card().classes("chart-card"):
            ui.label("Patrimonio total por fecha").classes("section-title")
            patrimonio = calcular_patrimonio_total_por_fecha(df_tx, df_inv)
            if not patrimonio.empty:
                fig = px.line(patrimonio, x="Fecha", y="Patrimonio total", markers=True)
                fig.update_yaxes(ticksuffix="€")
                ui.plotly(prepare_chart(fig)).classes("plotly-chart")
            else:
                ui.label("Aún no hay datos para calcular el patrimonio.").classes("text-gray-500")
