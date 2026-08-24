from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Optional

import pandas as pd


@dataclass
class MarketPriceResult:
    inversion: str
    ticker_yahoo: str
    valor_actual: Optional[float] = None
    precio: Optional[float] = None
    divisa_cotizacion: str = ""
    divisa_valoracion: str = "EUR"
    fecha_precio: str = ""
    tipo_cambio: float = 1.0
    error: str = ""


@dataclass
class YahooTickerInfo:
    ticker_yahoo: str
    nombre: str = ""
    divisa: str = ""
    error: str = ""


def buscar_info_ticker_yahoo(ticker_yahoo):
    ticker_yahoo = (ticker_yahoo or "").strip().upper()
    if not ticker_yahoo:
        return YahooTickerInfo(ticker_yahoo, error="Indica un ticker de Yahoo.")
    try:
        import yfinance as yf
    except ImportError:
        return YahooTickerInfo(ticker_yahoo, error="yfinance no está instalado.")

    _configure_yfinance_cache(yf)
    try:
        info = yf.Ticker(ticker_yahoo).info or {}
    except Exception:
        return YahooTickerInfo(ticker_yahoo, error="No se pudo consultar Yahoo Finance.")

    nombre = (
        info.get("shortName")
        or info.get("longName")
        or info.get("displayName")
        or ""
    )
    divisa = info.get("currency") or info.get("financialCurrency") or ""
    if not nombre and not divisa:
        return YahooTickerInfo(ticker_yahoo, error="No se encontró información para ese ticker.")
    return YahooTickerInfo(
        ticker_yahoo=ticker_yahoo,
        nombre=str(nombre or ticker_yahoo).strip(),
        divisa=str(divisa or "").strip().upper(),
    )


def obtener_valor_mercado(
    inversion,
    ticker_yahoo,
    unidades,
    fecha_valoracion,
    divisa_cotizacion="",
    divisa_valoracion="EUR",
):
    ticker_yahoo = (ticker_yahoo or "").strip().upper()
    divisa_valoracion = (divisa_valoracion or "EUR").strip().upper() or "EUR"
    divisa_cotizacion = (divisa_cotizacion or "").strip().upper()
    try:
        unidades = float(unidades or 0)
    except (TypeError, ValueError):
        return MarketPriceResult(inversion, ticker_yahoo, error="Unidades no válidas.")
    if not ticker_yahoo:
        return MarketPriceResult(inversion, ticker_yahoo, error="Ticker Yahoo no configurado.")
    if unidades <= 0:
        return MarketPriceResult(inversion, ticker_yahoo, error="No hay unidades abiertas.")

    try:
        import yfinance as yf
    except ImportError:
        return MarketPriceResult(inversion, ticker_yahoo, error="yfinance no está instalado.")

    _configure_yfinance_cache(yf)
    fecha_objetivo = _parse_date(fecha_valoracion)
    if fecha_objetivo is None:
        return MarketPriceResult(inversion, ticker_yahoo, error="Fecha de valoración no válida.")

    precio_data = _ultimo_cierre(yf, ticker_yahoo, fecha_objetivo)
    if precio_data is None:
        return MarketPriceResult(inversion, ticker_yahoo, error="Sin precio disponible.")

    precio, fecha_precio = precio_data
    if not divisa_cotizacion:
        divisa_cotizacion = _detectar_divisa(yf, ticker_yahoo)
    if not divisa_cotizacion:
        return MarketPriceResult(inversion, ticker_yahoo, error="Divisa de cotización no configurada.")

    divisa_fx = _normalizar_divisa_fx(divisa_cotizacion)
    tipo_cambio = 1.0
    if divisa_fx != divisa_valoracion:
        fx_data = _ultimo_cierre(yf, f"{divisa_fx}{divisa_valoracion}=X", fecha_objetivo)
        if fx_data is None:
            return MarketPriceResult(
                inversion,
                ticker_yahoo,
                precio=precio,
                divisa_cotizacion=divisa_cotizacion,
                divisa_valoracion=divisa_valoracion,
                fecha_precio=fecha_precio,
                error=f"Sin cambio {divisa_fx}/{divisa_valoracion}.",
            )
        tipo_cambio = fx_data[0]

    valor_actual = unidades * precio * tipo_cambio
    return MarketPriceResult(
        inversion=inversion,
        ticker_yahoo=ticker_yahoo,
        valor_actual=round(valor_actual, 2),
        precio=precio,
        divisa_cotizacion=divisa_cotizacion,
        divisa_valoracion=divisa_valoracion,
        fecha_precio=fecha_precio,
        tipo_cambio=tipo_cambio,
    )


def _parse_date(value):
    try:
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _configure_yfinance_cache(yf):
    try:
        from config import PRIVATE_DIR

        cache_dir = PRIVATE_DIR / "cache" / "yfinance"
        cache_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(yf, "set_tz_cache_location"):
            yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        pass


def _ultimo_cierre(yf, ticker, fecha_objetivo):
    start = fecha_objetivo - timedelta(days=14)
    end = fecha_objetivo + timedelta(days=1)
    try:
        history = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=False,
        )
    except Exception:
        return None
    if history is None or history.empty or "Close" not in history:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    index_dates = pd.to_datetime(closes.index).date
    valid = closes[index_dates <= fecha_objetivo]
    if valid.empty:
        return None
    last_date = pd.to_datetime(valid.index[-1]).date().isoformat()
    price = float(valid.iloc[-1])
    if not isfinite(price) or price <= 0:
        return None
    return price, last_date


def _detectar_divisa(yf, ticker):
    try:
        fast_info = yf.Ticker(ticker).fast_info
        currency = getattr(fast_info, "currency", None)
        if currency:
            return str(currency).strip().upper()
        if isinstance(fast_info, dict) and fast_info.get("currency"):
            return str(fast_info["currency"]).strip().upper()
    except Exception:
        pass
    return ""


def _normalizar_divisa_fx(divisa):
    divisa = (divisa or "").strip().upper()
    if divisa in {"GBX", "GBP", "GBP=X", "PENCE"}:
        return "GBP"
    return divisa
