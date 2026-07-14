"""Company/security name/market lookup, spanning TWSE (上市) + TPEx (上櫃).

Two kinds of feed per exchange, both full-market snapshots fetched once per
process and cached in-memory (same pattern as `twse.get_announcements`'s
`_announcement_cache`):
- The "company basic info" registries (t187ap03_L / mopsfin_t187ap03_O) only
  cover operating companies — ETFs, bond funds, etc. aren't companies and
  are absent from them.
- The daily-quotes feeds (STOCK_DAY_ALL / tpex_mainboard_quotes) cover every
  traded security on that exchange, so they fill in ETFs and anything else
  the company registry misses.
"""

import requests

TWSE_INFO_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_INFO_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TWSE_QUOTES_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_QUOTES_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_company_cache: dict[str, dict] | None = None


def _merge(companies: dict[str, dict], url: str, code_field: str, name_field: str, market: str) -> None:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        for row in resp.json():
            code = row.get(code_field)
            if code and code not in companies:
                companies[code] = {"name": row.get(name_field) or code, "market": market}
    except (requests.RequestException, ValueError):
        pass  # leave this source's names missing rather than fail the whole lookup


def _load_companies() -> dict[str, dict]:
    global _company_cache
    if _company_cache is not None:
        return _company_cache

    companies: dict[str, dict] = {}
    _merge(companies, TWSE_INFO_URL, "公司代號", "公司簡稱", "TWSE")
    _merge(companies, TPEX_INFO_URL, "SecuritiesCompanyCode", "CompanyAbbreviation", "TPEx")
    _merge(companies, TWSE_QUOTES_URL, "Code", "Name", "TWSE")
    _merge(companies, TPEX_QUOTES_URL, "SecuritiesCompanyCode", "CompanyName", "TPEx")

    if companies:
        _company_cache = companies
    return companies


def get_company_info(symbol: str) -> dict | None:
    symbol = symbol.strip().upper()
    return _load_companies().get(symbol)
