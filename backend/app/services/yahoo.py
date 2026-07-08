import asyncio

import pandas as pd
import yfinance as yf

TWSE_SUFFIX = ".TW"
TPEX_SUFFIX = ".TWO"


class StockNotFoundError(Exception):
    pass


def _fetch_history_sync(yahoo_symbol: str, interval: str, period: str):
    ticker = yf.Ticker(yahoo_symbol)
    return ticker.history(period=period, interval=interval, auto_adjust=True)


async def get_price_dataframe(
    symbol: str, interval: str = "1d", period: str = "6mo"
) -> tuple[pd.DataFrame, str]:
    """Fetch OHLCV history for a Taiwan stock code via Yahoo Finance as a DataFrame.

    Tries the TWSE (.TW) suffix first, falls back to TPEx (.TWO) since a bare
    numeric code alone doesn't say which exchange the stock is listed on.
    Rows with NaN OHLC (e.g. the most recent day before the session finalizes)
    are dropped since they aren't usable candles or indicator inputs.
    """
    symbol = symbol.strip().upper()
    for suffix in (TWSE_SUFFIX, TPEX_SUFFIX):
        yahoo_symbol = f"{symbol}{suffix}"
        df = await asyncio.to_thread(_fetch_history_sync, yahoo_symbol, interval, period)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if not df.empty:
            return df, yahoo_symbol
    raise StockNotFoundError(f"No data found for symbol '{symbol}' on Yahoo Finance")


def dataframe_to_candles(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "time": index.strftime("%Y-%m-%d"),
            "open": round(float(row.Open), 2),
            "high": round(float(row.High), 2),
            "low": round(float(row.Low), 2),
            "close": round(float(row.Close), 2),
            "volume": int(row.Volume),
        }
        for index, row in df.iterrows()
    ]


async def get_price_history(symbol: str, interval: str = "1d", period: str = "6mo") -> dict:
    df, yahoo_symbol = await get_price_dataframe(symbol, interval=interval, period=period)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "interval": interval,
        "period": period,
        "adjusted": True,
        "candles": dataframe_to_candles(df),
    }
