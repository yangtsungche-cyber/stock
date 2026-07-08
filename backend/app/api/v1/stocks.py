import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.services import granville, indicators, twse
from app.services.yahoo import StockNotFoundError, get_price_dataframe, get_price_history

router = APIRouter(prefix="/stocks", tags=["stocks"])

VALID_INTERVALS = {"1d", "1wk", "1mo"}


@router.get("/{symbol}/prices")
async def get_prices(
    symbol: str,
    interval: str = Query("1d", description="1d=日K, 1wk=週K, 1mo=月K"),
    period: str = Query("6mo", description="資料範圍，例如 1mo, 6mo, 1y, 5y, max"),
) -> dict:
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"interval must be one of {sorted(VALID_INTERVALS)}")
    try:
        return await get_price_history(symbol, interval=interval, period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{symbol}/indicators")
async def get_indicators(
    symbol: str,
    period: str = Query("2y", description="計算指標所需的資料範圍，需足夠長才能算出 240 日均線"),
) -> dict:
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        **indicators.compute_all(df),
    }


@router.get("/{symbol}/granville")
async def get_granville(
    symbol: str,
    period: str = Query("2y", description="計算所需的資料範圍"),
) -> dict:
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_all(df)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        **granville.analyze(df, ind),
    }


@router.get("/{symbol}/margin")
async def get_margin(
    symbol: str,
    days: int = Query(20, ge=1, le=60, description="近 N 個交易日"),
) -> dict:
    history = await asyncio.to_thread(twse.get_margin_history, symbol, days)
    return {"symbol": symbol.strip().upper(), "history": history}


@router.get("/{symbol}/institutional")
async def get_institutional(
    symbol: str,
    days: int = Query(20, ge=1, le=60, description="近 N 個交易日"),
) -> dict:
    history = await asyncio.to_thread(twse.get_institutional_history, symbol, days)
    return {"symbol": symbol.strip().upper(), "history": history}


@router.get("/{symbol}/announcements")
async def get_announcements(symbol: str) -> dict:
    announcements = await asyncio.to_thread(twse.get_announcements, symbol)
    return {"symbol": symbol.strip().upper(), "announcements": announcements}
