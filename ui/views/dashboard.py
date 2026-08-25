import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from nicegui import ui

from db.queries import cargar_datos
from services.analytics import calcular_liquidez_por_fecha, calcular_patrimonio_total_por_fecha
from ui.components import (
    aplicar_tema_grafica,
    color_por_signo,
    formato_euros_sin_signo,
    formato_numero,
    formato_porcentaje,
    metric_card,
)


COLOR_PRIMARY = "#2563EB"
COLOR_POSITIVE = "#10B981"
COLOR_TEXT_MUTED = "#64748B"
COLOR_GRID_SUBTLE = "#F1F5F9"
CHART_COLORS = ["#3B82F6", "#06B6D4", "#8B5CF6", "#F97316", "#F43F5E"]


def prepare_chart(fig, height=420, is_dark=False):
    fig.update_layout(
        autosize=True,
        height=height,
        margin={"l": 24, "r": 24, "t": 48, "b": 24},
        separators=",.",
    )
    return aplicar_tema_grafica(fig, is_dark)


def formato_euros_hover(valor):
    return formato_numero(valor, sufijo=" €")


def rgba_from_hex(color, opacity):
    red, green, blue = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {opacity})"


def prepare_financial_area_chart(data, x_col, y_col, color, is_dark=False):
    chart_data = data.copy()
    chart_data[x_col] = pd.to_datetime(chart_data[x_col])
    chart_data["Fecha hover"] = chart_data[x_col].dt.strftime("%d/%m/%Y")
    chart_data["Importe hover"] = chart_data[y_col].apply(formato_euros_hover)

    fig = go.Figure(
        go.Scatter(
            x=chart_data[x_col],
            y=chart_data[y_col],
            customdata=chart_data[["Fecha hover", "Importe hover"]],
            mode="lines",
            line={"color": color, "width": 3, "shape": "spline", "smoothing": 0.4},
            marker={"color": color, "size": 8},
            fill="tozeroy",
            fillgradient={
                "type": "vertical",
                "colorscale": [
                    [0, rgba_from_hex(color, 0.02)],
                    [1, rgba_from_hex(color, 0.24)],
                ],
            },
            hovertemplate="%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
        )
    )
    fig.update_layout(
        hovermode="closest",
        showlegend=False,
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    fig.update_yaxes(
        showgrid=False,
        zeroline=False,
        ticksuffix="\u20ac",
        tickfont={"color": COLOR_TEXT_MUTED},
        linecolor=COLOR_GRID_SUBTLE,
    )
    return prepare_chart(fig, is_dark=is_dark)


def render_saldo_global(usuario, is_dark=False):
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
                    formato_porcentaje(balance_inversiones_pct, signed=True)
                ).classes(f"text-sm font-semibold {color_por_signo(balance_inversiones_pct)}")

    with ui.row().classes("w-full gap-4 items-stretch"):
        with ui.card().classes("chart-card"):
            ui.label("Distribución de Liquidez por Cuenta").classes("section-title")
            if not df_tx.empty:
                distribucion = df_tx.groupby("cuenta")["importe"].sum().reset_index()
                distribucion = distribucion[distribucion["importe"] > 0]
                if not distribucion.empty:
                    fig = px.pie(
                        distribucion,
                        values="importe",
                        names="cuenta",
                        hole=0.4,
                        color_discrete_sequence=CHART_COLORS,
                    )
                    ui.plotly(prepare_chart(fig, is_dark=is_dark)).classes("plotly-chart")
                else:
                    ui.label("No hay saldo positivo en las cuentas.").classes("text-gray-500")
            else:
                ui.label("Aún no hay transacciones registradas.").classes("text-gray-500")

        with ui.card().classes("chart-card"):
            ui.label("Distribución de Inversiones").classes("section-title")
            if not df_inv_latest.empty:
                fig = px.pie(
                    df_inv_latest,
                    values="valor_actual",
                    names="inversion",
                    hole=0.4,
                    color_discrete_sequence=CHART_COLORS,
                )
                ui.plotly(prepare_chart(fig, is_dark=is_dark)).classes("plotly-chart")
            else:
                ui.label("Aún no hay inversiones registradas.").classes("text-gray-500")

    with ui.row().classes("w-full gap-4 items-stretch"):
        with ui.card().classes("chart-card"):
            ui.label("Liquidez total por fecha").classes("section-title")
            liquidez = calcular_liquidez_por_fecha(df_tx)
            if not liquidez.empty:
                fig = prepare_financial_area_chart(liquidez, "Fecha", "Liquidez", COLOR_PRIMARY, is_dark=is_dark)
                ui.plotly(fig).classes("plotly-chart")
            else:
                ui.label("Aún no hay transacciones registradas.").classes("text-gray-500")
        with ui.card().classes("chart-card"):
            ui.label("Patrimonio total por fecha").classes("section-title")
            patrimonio = calcular_patrimonio_total_por_fecha(df_tx, df_inv)
            if not patrimonio.empty:
                fig = prepare_financial_area_chart(
                    patrimonio, "Fecha", "Patrimonio total", COLOR_POSITIVE, is_dark=is_dark
                )
                ui.plotly(fig).classes("plotly-chart")
            else:
                ui.label("Aún no hay datos para calcular el patrimonio.").classes("text-gray-500")
