"""Thin FinMind client for multi-year fundamentals (財報/資產負債/現金流/股利).

FinMind's free tier allows per-stock calls (specifying `data_id`) with no
history-window limit — one call returns a symbol's full quarterly history
back to ~2010 — but blocks bulk all-stock pulls (HTTP 400) unless paid.
That's fine here: this module only ever fetches one symbol at a time, for
the individual-stock 基本面分析 tab. A future full-market screening batch
job is a separate concern (see memory `stock-v32-fundamental-data-research`).

Same in-process-cache-for-process-lifetime pattern as `twse.py`/`company.py`
— fundamentals only change quarterly, so re-fetching per request is wasted
work and eats into the hourly rate limit for no benefit.
"""

from datetime import date, timedelta

import requests

from app.core.config import get_settings

BASE_URL = "https://api.finmindtrade.com/api/v4/data"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

HISTORY_START = (date.today() - timedelta(days=365 * 6)).isoformat()  # ~6y, covers 近五年 checks

_cache: dict[tuple[str, str], list[dict]] = {}


def _fetch(dataset: str, symbol: str) -> list[dict]:
    key = (dataset, symbol)
    if key in _cache:
        return _cache[key]

    settings = get_settings()
    params = {"dataset": dataset, "data_id": symbol, "start_date": HISTORY_START}
    if settings.finmind_token:
        params["token"] = settings.finmind_token

    try:
        resp = requests.get(BASE_URL, params=params, headers=_HEADERS, timeout=20)
        data = resp.json().get("data", [])
    except (requests.RequestException, ValueError):
        data = []  # transient failure — don't cache, a later request may succeed

    if data:
        _cache[key] = data
    return data


def get_financial_statements(symbol: str) -> list[dict]:
    """綜合損益表：Revenue/GrossProfit/OperatingIncome/IncomeAfterTaxes/EPS per quarter."""
    return _fetch("TaiwanStockFinancialStatements", symbol)


def get_balance_sheet(symbol: str) -> list[dict]:
    """資產負債表：TotalAssets/CurrentAssets/CurrentLiabilities/Equity per quarter."""
    return _fetch("TaiwanStockBalanceSheet", symbol)


def get_cash_flow(symbol: str) -> list[dict]:
    """現金流量表：CashFlowsFromOperatingActivities/PropertyAndPlantAndEquipment per quarter."""
    return _fetch("TaiwanStockCashFlowsStatement", symbol)


def get_dividend(symbol: str) -> list[dict]:
    """股利政策：CashEarningsDistribution per fiscal year (配息年數/穩定度)."""
    return _fetch("TaiwanStockDividend", symbol)
