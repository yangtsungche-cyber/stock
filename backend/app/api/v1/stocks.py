import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.services import chips, granville, indicators, layers, twse
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


@router.get("/{symbol}/layers")
async def get_layers(
    symbol: str,
    period: str = Query("2y", description="計算指標所需的資料範圍"),
) -> dict:
    """第三～七層：KD、MACD、均線乖離率、RSI、成交量。"""
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_all(df)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        **layers.analyze_layers(ind),
    }


@router.get("/{symbol}/margin")
async def get_margin(
    symbol: str,
    days: int = Query(20, ge=1, le=60, description="近 N 個交易日"),
) -> dict:
    history = await asyncio.to_thread(twse.get_margin_history, symbol, days)
    analysis = chips.analyze_margin(history)
    return {"symbol": symbol.strip().upper(), **analysis}


@router.get("/{symbol}/institutional")
async def get_institutional(
    symbol: str,
    days: int = Query(20, ge=1, le=60, description="近 N 個交易日"),
) -> dict:
    history = await asyncio.to_thread(twse.get_institutional_history, symbol, days)
    analysis = chips.analyze_institutional(history)
    return {"symbol": symbol.strip().upper(), "history": history, **analysis}


@router.get("/{symbol}/chips")
async def get_chips(
    symbol: str,
    days: int = Query(20, ge=1, le=60, description="近 N 個交易日"),
) -> dict:
    """第八層：籌碼面綜合訊號（融資融券 + 三大法人），供後續決策引擎使用。"""
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, days),
        asyncio.to_thread(twse.get_institutional_history, symbol, days),
    )
    return {"symbol": symbol.strip().upper(), **chips.analyze(margin_history, institutional_history)}


@router.get("/{symbol}/announcements")
async def get_announcements(symbol: str) -> dict:
    announcements = await asyncio.to_thread(twse.get_announcements, symbol)
    return {"symbol": symbol.strip().upper(), "announcements": announcements}
