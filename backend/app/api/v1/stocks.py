import asyncio
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.services import (
    chips,
    combined,
    company,
    decision,
    fundamentals,
    granville,
    indicators,
    layers,
    playbook,
    report,
    twse,
    waves,
)
from app.services.yahoo import StockNotFoundError, get_price_dataframe, get_price_history

router = APIRouter(prefix="/stocks", tags=["stocks"])

VALID_INTERVALS = {"1d", "1wk", "1mo"}
BATCH_REPORT_MAX_SYMBOLS = 5


class BatchReportRequest(BaseModel):
    symbols: list[str]


@router.get("/search")
async def search_stocks(q: str = Query("", description="股票代號前綴或名稱關鍵字")) -> dict:
    """即時搜尋建議，取代舊的 4 檔硬編碼假資料——查真實的 TWSE/TPEx/興櫃 全市場登記清單。"""
    results = await asyncio.to_thread(company.search_companies, q)
    return {"results": results}


@router.get("/{symbol}/info")
async def get_info(symbol: str) -> dict:
    """Company name + market (TWSE/TPEx), for the header display."""
    info = await asyncio.to_thread(company.get_company_info, symbol)
    if info is None:
        raise HTTPException(status_code=404, detail=f"找不到股票代號 '{symbol}' 的公司資料")
    return {"symbol": symbol.strip().upper(), **info}


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


@router.get("/{symbol}/waves")
async def get_waves(
    symbol: str,
    period: str = Query("2y", description="計算波浪所需的資料範圍"),
) -> dict:
    """第二層：波浪理論（ZigZag 拐點 + 艾略特波浪硬性規則檢核）。"""
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": df.index[-1].strftime("%Y-%m-%d"),
        **waves.analyze(df),
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


@router.get("/{symbol}/decision")
async def get_decision(
    symbol: str,
    period: str = Query("2y", description="計算指標所需的資料範圍"),
    days: int = Query(20, ge=1, le=60, description="籌碼面近 N 個交易日"),
) -> dict:
    """決策摘要：Adaptive Weighted Decision Engine，整合各層訊號產生綜合買賣判斷。"""
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_all(df)
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, days),
        asyncio.to_thread(twse.get_institutional_history, symbol, days),
    )
    granville_result = granville.analyze(df, ind)
    waves_result = waves.analyze(df)
    layers_result = layers.analyze_layers(ind)
    chips_result = chips.analyze(margin_history, institutional_history)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        **decision.analyze(granville_result, waves_result, layers_result, chips_result),
    }


@router.get("/{symbol}/combined")
async def get_combined(
    symbol: str,
    period: str = Query("2y", description="計算指標所需的資料範圍"),
    days: int = Query(20, ge=1, le=60, description="籌碼面近 N 個交易日"),
) -> dict:
    """技術面 × 基本面綜合判斷：整合決策引擎的技術面燈號與基本面AI評等。"""
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_all(df)
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, days),
        asyncio.to_thread(twse.get_institutional_history, symbol, days),
    )
    granville_result = granville.analyze(df, ind)
    waves_result = waves.analyze(df)
    layers_result = layers.analyze_layers(ind)
    chips_result = chips.analyze(margin_history, institutional_history)
    decision_result = decision.analyze(granville_result, waves_result, layers_result, chips_result)
    fundamentals_result = await asyncio.to_thread(fundamentals.analyze, symbol)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        "technical_score": decision_result["score"],
        "technical_verdict": decision_result["verdict"],
        "grade": decision_result["grade"],
        **combined.analyze(decision_result, fundamentals_result),
    }


@router.get("/{symbol}/playbook")
async def get_playbook(
    symbol: str,
    period: str = Query("2y", description="計算指標所需的資料範圍"),
    days: int = Query(20, ge=1, le=60, description="籌碼面近 N 個交易日"),
) -> dict:
    """Investment Playbook：依決策引擎結果推導進出場價位、部位建議與失效條件。"""
    try:
        df, yahoo_symbol = await get_price_dataframe(symbol, interval="1d", period=period)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ind = indicators.compute_all(df)
    margin_history, institutional_history = await asyncio.gather(
        asyncio.to_thread(twse.get_margin_history, symbol, days),
        asyncio.to_thread(twse.get_institutional_history, symbol, days),
    )
    granville_result = granville.analyze(df, ind)
    waves_result = waves.analyze(df)
    layers_result = layers.analyze_layers(ind)
    chips_result = chips.analyze(margin_history, institutional_history)
    decision_result = decision.analyze(granville_result, waves_result, layers_result, chips_result)
    return {
        "symbol": symbol.strip().upper(),
        "yahoo_symbol": yahoo_symbol,
        "date": ind["dates"][-1],
        "score": decision_result["score"],
        "verdict": decision_result["verdict"],
        "verdict_label": decision_result["verdict_label"],
        "grade": decision_result["grade"],
        **playbook.analyze(ind, granville_result, waves_result, chips_result, decision_result, symbol=symbol),
    }


@router.get("/{symbol}/fundamentals")
async def get_fundamentals(symbol: str) -> dict:
    """基本面分析頁籤：公司體質／獲利能力／成長能力／股東回報 + AI基本面評等。"""
    return await asyncio.to_thread(fundamentals.analyze, symbol)


@router.get("/{symbol}/announcements")
async def get_announcements(symbol: str) -> dict:
    announcements = await asyncio.to_thread(twse.get_announcements, symbol)
    return {"symbol": symbol.strip().upper(), "announcements": announcements}


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    # Chinese filenames aren't valid in the plain `filename=` parameter — use the RFC 5987
    # `filename*=UTF-8''...` form (with an ASCII fallback) so this downloads with a readable
    # name instead of browsers falling back to the URL's last path segment.
    encoded = quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"report.pdf\"; filename*=UTF-8''{encoded}"},
    )


@router.get("/{symbol}/report.pdf")
async def get_report_pdf(symbol: str) -> Response:
    """單一股票完整分析報告 PDF——避免重複查詢，也方便分享給他人或其他 AI 參考。"""
    full = await report.analyze_full(symbol)
    if full.get("error"):
        raise HTTPException(status_code=404, detail=full["error"])
    pdf_bytes = await asyncio.to_thread(report.render_pdf, [full])
    return _pdf_response(pdf_bytes, f"{full['symbol']}_{full['name']}_分析報告.pdf")


@router.post("/batch-report")
async def post_batch_report(body: BatchReportRequest) -> Response:
    """批次分析報告 PDF（最多 5 檔）——一次查完直接下載，不在網頁上呈現。"""
    symbols = [s.strip().upper() for s in body.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=422, detail="請至少指定一檔股票代號")
    if len(symbols) > BATCH_REPORT_MAX_SYMBOLS:
        raise HTTPException(status_code=422, detail=f"一次最多查詢 {BATCH_REPORT_MAX_SYMBOLS} 檔股票")

    reports = await asyncio.gather(*(report.analyze_full(s) for s in symbols))
    # V3.2：訊號品質 D 級（訊號基礎過窄，系統本來就不建議當方向性訊號）直接跳過、不產出
    # 該檔報告——但抓取失敗（error 不為 None）的個股仍要保留，讓使用者知道那檔查詢失敗，
    # 跟「查得到但訊號品質太差被過濾」是兩種不同狀況，不能都吃掉不呈現。
    filtered = [r for r in reports if r.get("error") or r["decision"]["grade"] != "D"]
    if not filtered:
        raise HTTPException(status_code=422, detail="所選股票訊號品質皆為 D 級（訊號基礎過窄），已全數略過，無報告可產生")
    pdf_bytes = await asyncio.to_thread(report.render_pdf, filtered)
    return _pdf_response(pdf_bytes, "批次分析報告.pdf")
