from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse

from db.queries import actualizar_logo_activo
from services.market_prices import _configure_yfinance_cache


@dataclass
class LogoSyncResult:
    inversion: str
    ticker_yahoo: str
    logo_url: str
    used_duckduckgo: bool = False


def url_avatar_fallback(inversion):
    nombre_activo = str(inversion or "Activo")
    nombre_normalizado = nombre_activo.lower()
    reglas = [
        (("oro", "gold"), "F59E0B", "fff", "AU"),
        (("cripto", "criptomoneda", "crypto", "btc", "bitcoin"), "F7931A", "fff", "₿"),
        (("world", "global"), "0EA5E9", "fff", "🌍"),
        (("s&p", "sp500", "us ", "eeuu", "nasdaq"), "1E3A8A", "fff", "US"),
        (("europe", "europa", "eurostoxx"), "1D4ED8", "FBBF24", "EU"),
        (("emerging", "emergentes"), "059669", "fff", "EM"),
        (("bono", "bond", "renta fija"), "64748B", "fff", "FI"),
        (("msci",), "1E293B", "fff", "MSCI"),
    ]
    for keywords, background, color, name in reglas:
        if any(keyword in nombre_normalizado for keyword in keywords):
            return (
                "https://ui-avatars.com/api/"
                f"?name={quote_plus(name)}&background={background}&color={color}&bold=true&size=128"
            )

    nombre = quote_plus(nombre_activo)
    return (
        "https://ui-avatars.com/api/"
        f"?name={nombre}&background=EFF6FF&color=2563EB&bold=true&size=128"
    )


def _extraer_dominio_logo(website):
    website = str(website or "").strip()
    if not website:
        return ""
    parsed = urlparse(website if "://" in website else f"https://{website}")
    dominio = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if dominio.startswith("www."):
        dominio = dominio[4:]
    return dominio if "." in dominio else ""


def _consultar_website_yfinance(ticker_yahoo):
    import yfinance as yf

    _configure_yfinance_cache(yf)
    info = yf.Ticker(ticker_yahoo).info or {}
    return (
        info.get("website")
        or info.get("websiteUrl")
        or info.get("weburl")
        or ""
    )


async def sincronizar_logo_activo(inversion, ticker_yahoo, usuario=None):
    if usuario is None:
        from db.connection import current_username

        usuario = current_username()
    resultado = await obtener_logo_activo(inversion, ticker_yahoo)
    actualizar_logo_activo(inversion, resultado.logo_url, usuario)
    return resultado


async def obtener_logo_activo(inversion, ticker_yahoo):
    ticker_yahoo = (ticker_yahoo or "").strip().upper()
    logo_url = url_avatar_fallback(inversion)
    used_duckduckgo = False

    if ticker_yahoo:
        try:
            import asyncio

            website = await asyncio.to_thread(_consultar_website_yfinance, ticker_yahoo)
            dominio = _extraer_dominio_logo(website)
            if dominio:
                logo_url = f"https://icons.duckduckgo.com/ip3/{dominio}.ico"
                used_duckduckgo = True
        except Exception:
            logo_url = url_avatar_fallback(inversion)

    return LogoSyncResult(
        inversion=inversion,
        ticker_yahoo=ticker_yahoo,
        logo_url=logo_url,
        used_duckduckgo=used_duckduckgo,
    )
