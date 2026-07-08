import time
from datetime import date, timedelta

import requests

MARGIN_URL = "https://www.twse.com.tw/exchangeReport/MI_MARGN"
INSTITUTIONAL_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
ANNOUNCEMENT_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"

MARGIN_FIELDS = [
    "code",
    "name",
    "margin_buy",
    "margin_sell",
    "margin_cash_redemption",
    "margin_prev_balance",
    "margin_today_balance",
    "margin_next_day_limit",
    "short_buy",
    "short_sell",
    "short_stock_redemption",
    "short_prev_balance",
    "short_today_balance",
    "short_next_day_limit",
    "offset",
    "note",
]

INSTITUTIONAL_FIELDS = [
    "code",
    "name",
    "foreign_buy",
    "foreign_sell",
    "foreign_net",
    "foreign_dealer_buy",
    "foreign_dealer_sell",
    "foreign_dealer_net",
    "trust_buy",
    "trust_sell",
    "trust_net",
    "dealer_net",
    "dealer_self_buy",
    "dealer_self_sell",
    "dealer_self_net",
    "dealer_hedge_buy",
    "dealer_hedge_sell",
    "dealer_hedge_net",
    "total_net",
]

# Process-local cache only. This is a stopgap until Redis is wired in
# (Docker isn't available on this dev machine yet) — same-day full-market
# snapshots are reused instead of re-fetched per stock lookup.
_margin_cache: dict[str, dict[str, dict] | None] = {}
_institutional_cache: dict[str, dict[str, dict] | None] = {}
_announcement_cache: list[dict] | None = None

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _parse_number(value: str) -> int:
    value = (value or "").replace(",", "").strip()
    if not value:
        return 0
    return int(value)


def _roc_to_iso(roc: str) -> str:
    if not roc or len(roc) < 7:
        return roc
    year = int(roc[:3]) + 1911
    return f"{year}-{roc[3:5]}-{roc[5:7]}"


def _fetch_margin_table(date_str: str) -> dict[str, dict] | None:
    if date_str in _margin_cache:
        return _margin_cache[date_str]

    resp = requests.get(
        MARGIN_URL,
        params={"response": "json", "date": date_str, "selectType": "ALL"},
        headers=_HEADERS,
        timeout=10,
    )
    data = resp.json()
    if data.get("stat") != "OK":
        _margin_cache[date_str] = None
        return None

    table = next((t for t in data.get("tables", []) if "彙總" in t.get("title", "")), None)
    if not table:
        _margin_cache[date_str] = None
        return None

    rows = {row[0]: dict(zip(MARGIN_FIELDS, row)) for row in table["data"]}
    _margin_cache[date_str] = rows
    return rows


def _fetch_institutional_table(date_str: str) -> dict[str, dict] | None:
    if date_str in _institutional_cache:
        return _institutional_cache[date_str]

    resp = requests.get(
        INSTITUTIONAL_URL,
        params={"response": "json", "date": date_str, "selectType": "ALL"},
        headers=_HEADERS,
        timeout=10,
    )
    data = resp.json()
    if data.get("stat") != "OK":
        _institutional_cache[date_str] = None
        return None

    rows = {row[0]: dict(zip(INSTITUTIONAL_FIELDS, row)) for row in data.get("data", [])}
    _institutional_cache[date_str] = rows
    return rows


def _collect_history(
    symbol: str,
    days: int,
    fetch_table,
    numeric_fields: list[str],
    max_lookback: int = 60,
) -> list[dict]:
    results = []
    current = date.today()
    lookback = 0

    while len(results) < days and lookback < max_lookback:
        current -= timedelta(days=1)
        lookback += 1
        if current.weekday() >= 5:
            continue

        table = fetch_table(current.strftime("%Y%m%d"))
        if table is None:
            continue

        row = table.get(symbol)
        if row is None:
            continue

        parsed = {k: (_parse_number(v) if k in numeric_fields else v) for k, v in row.items()}
        results.append({"date": current.isoformat(), **parsed})
        time.sleep(0.15)

    results.reverse()
    return results


def get_margin_history(symbol: str, days: int = 20) -> list[dict]:
    symbol = symbol.strip().upper()
    numeric_fields = [f for f in MARGIN_FIELDS if f not in ("code", "name", "note")]
    return _collect_history(symbol, days, _fetch_margin_table, numeric_fields)


def get_institutional_history(symbol: str, days: int = 20) -> list[dict]:
    symbol = symbol.strip().upper()
    numeric_fields = [f for f in INSTITUTIONAL_FIELDS if f not in ("code", "name")]
    return _collect_history(symbol, days, _fetch_institutional_table, numeric_fields)


def get_announcements(symbol: str) -> list[dict]:
    global _announcement_cache
    symbol = symbol.strip().upper()

    if _announcement_cache is None:
        resp = requests.get(ANNOUNCEMENT_URL, headers=_HEADERS, timeout=15)
        _announcement_cache = resp.json()

    return [
        {
            "date": _roc_to_iso(row.get("發言日期", "")),
            "time": row.get("發言時間", ""),
            "subject": row.get("主旨 ", "").strip(),
            "fact_date": _roc_to_iso(row.get("事實發生日", "")),
            "description": row.get("說明", ""),
        }
        for row in _announcement_cache
        if row.get("公司代號") == symbol
    ]
