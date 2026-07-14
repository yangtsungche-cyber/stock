"""Company name/market lookup, spanning TWSE (上市) + TPEx (上櫃) company-info
open-data feeds. Each feed is a full-market snapshot (~900-1100 rows) that
rarely changes intra-day, so it's fetched once per process and cached
in-memory — same pattern as `twse.get_announcements`'s `_announcement_cache`.
"""

import requests

TWSE_INFO_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_INFO_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_company_cache: dict[str, dict] | None = None


def _load_companies() -> dict[str, dict]:
    global _company_cache
    if _company_cache is not None:
        return _company_cache

    companies: dict[str, dict] = {}

    try:
        resp = requests.get(TWSE_INFO_URL, headers=_HEADERS, timeout=15)
        for row in resp.json():
            code = row.get("公司代號")
            if code:
                companies[code] = {"name": row.get("公司簡稱") or code, "market": "TWSE"}
    except (requests.RequestException, ValueError):
        pass  # leave TWSE names missing rather than fail the whole lookup

    try:
        resp = requests.get(TPEX_INFO_URL, headers=_HEADERS, timeout=15)
        for row in resp.json():
            code = row.get("SecuritiesCompanyCode")
            if code and code not in companies:
                companies[code] = {"name": row.get("CompanyAbbreviation") or code, "market": "TPEx"}
    except (requests.RequestException, ValueError):
        pass

    if companies:
        _company_cache = companies
    return companies


def get_company_info(symbol: str) -> dict | None:
    symbol = symbol.strip().upper()
    return _load_companies().get(symbol)
