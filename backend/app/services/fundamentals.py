"""基本面分析：公司體質／獲利能力／成長能力／股東回報 + AI基本面評等。

Same philosophy as every other analysis module here — plain deterministic
rules over already-fetched data (no LLM call). Multi-year figures come from
`finmind.py` (quarterly financial statements/balance sheet/cash flow/
dividend); today's valuation snapshot (PE/dividend yield) comes straight
from TWSE/TPEx, same dual-exchange pattern as `company.py`.

The rating thresholds below double as this stock's individual pass/fail
checklist AND (per the V3.2 spec's "all thresholds centrally configured"
principle) the criteria a future full-market screening batch job should
reuse for building the 基本面候選池 — don't fork a second copy of these
numbers elsewhere.

Scope note: "本益比低於產業平均" from the spec needs an industry-wide
average, which requires scanning every stock in the industry — that's a
batch/screening-time concern, not something a single-stock lookup can
answer. This module reports the stock's own PE/yield but leaves the
industry comparison for the future batch job.
"""

from datetime import date, timedelta

import requests

from app.services import finmind

EPS_GROWTH_MIN = 15.0  # percent, TTM EPS vs prior TTM EPS
ROE_MIN = 12.0  # percent
REVENUE_CAGR_MIN = 10.0  # percent, 3-year
GROSS_MARGIN_TOLERANCE = -0.5  # pp; "持平或上升" allows a small YoY dip before failing
DEBT_RATIO_MAX = 50.0  # percent
CURRENT_RATIO_MIN = 120.0  # percent
DIVIDEND_YIELD_MIN = 3.0  # percent

# V3.2：基本面三模組加權重構——checklist 8 項不再攤平算通過比例，改成先分進
# 成長性(Growth)/獲利能力(Profitability)/財務安全(Safety) 三桶，各桶內仍是「通過項數/
# 該桶項數」的布林計數（不改成連續分數，維持改動幅度最小），再依權重加總。
GROWTH_KEYS = {"eps_growth", "revenue_cagr"}
PROFITABILITY_KEYS = {"roe", "gross_margin_trend"}
SAFETY_KEYS = {"debt_ratio", "free_cash_flow", "current_ratio", "dividend_yield"}

GROWTH_WEIGHT = 0.5
PROFITABILITY_WEIGHT = 0.3
SAFETY_WEIGHT = 0.2

# 成長懲罰因子：兩項成長指標(EPS成長率、營收CAGR)皆未達標時，Growth 模組得分為 0（兩項
# 之外唯一低於 40% 的可能值，50/100 都已經 >=40%），基本面總分強制打 8 折——過濾「殖利率
# 高但沒有成長動能」的股票。
GROWTH_PENALTY_THRESHOLD = 40.0  # percent, Growth 模組自己的得分
GROWTH_PENALTY_MULTIPLIER = 0.8

TWSE_VALUATION_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TPEX_VALUATION_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

_valuation_cache: dict[str, dict] | None = None


def _pivot(rows: list[dict]) -> dict[str, dict[str, float]]:
    """[{date, type, value}, ...] -> {date: {type: value}}, sorted by date ascending."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        out.setdefault(row["date"], {})[row["type"]] = row["value"]
    return dict(sorted(out.items()))


def _load_valuation() -> dict[str, dict]:
    global _valuation_cache
    if _valuation_cache is not None:
        return _valuation_cache

    valuation: dict[str, dict] = {}
    try:
        resp = requests.get(TWSE_VALUATION_URL, headers=_HEADERS, timeout=15)
        for row in resp.json():
            code = row.get("Code")
            if not code:
                continue
            valuation[code] = {
                "pe_ratio": _to_float(row.get("PEratio")),
                "dividend_yield": _to_float(row.get("DividendYield")),
                "pb_ratio": _to_float(row.get("PBratio")),
            }
    except (requests.RequestException, ValueError):
        pass

    try:
        resp = requests.get(TPEX_VALUATION_URL, headers=_HEADERS, timeout=15)
        for row in resp.json():
            code = row.get("SecuritiesCompanyCode")
            if not code or code in valuation:
                continue
            valuation[code] = {
                "pe_ratio": _to_float(row.get("PriceEarningRatio")),
                "dividend_yield": _to_float(row.get("YieldRatio")),
                "pb_ratio": _to_float(row.get("PriceBookRatio")),
            }
    except (requests.RequestException, ValueError):
        pass

    if valuation:
        _valuation_cache = valuation
    return valuation


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ttm(quarters: list[dict[str, float]], field: str, offset: int = 0) -> float | None:
    """Sum of `field` over 4 quarters, `offset` quarters back from the latest."""
    end = len(quarters) - offset
    start = end - 4
    if start < 0 or end <= 0:
        return None
    window = quarters[start:end]
    if len(window) < 4:
        return None
    return sum(q.get(field, 0.0) for q in window)


def _annual_revenue_by_year(fs_by_date: dict[str, dict[str, float]]) -> dict[int, float]:
    by_year: dict[int, list[float]] = {}
    for d, fields in fs_by_date.items():
        if "Revenue" not in fields:
            continue
        by_year.setdefault(int(d[:4]), []).append(fields["Revenue"])
    return {year: sum(vals) for year, vals in by_year.items() if len(vals) == 4}


def analyze(symbol: str) -> dict:
    symbol = symbol.strip().upper()

    # FinMind 額度用盡（HTTP 402）時要跟「這檔真的沒有財報資料」分開處理——兩者原本都會
    # 讓 fs_by_date/bs_by_date 變空，導致額度用盡時顯示「可能為 ETF」這種誤導訊息（曾實際
    # 發生在 6197 佳必琪、2472 立隆電這兩檔真實上市公司身上，用真實 API 回應驗證過：狀態碼
    # 402 "Requests reach the upper limit"，不是代號對應失效或欄位改版）。
    try:
        fs_by_date = _pivot(finmind.get_financial_statements(symbol))
        bs_by_date = _pivot(finmind.get_balance_sheet(symbol))
        cf_by_date = _pivot(finmind.get_cash_flow(symbol))
        dividend_rows = finmind.get_dividend(symbol)
    except finmind.FinMindUnavailableError as e:
        reason = (
            "FinMind API 已達呼叫上限，暫時無法取得財報資料，請稍後再試"
            if e.status_code == 402
            else f"FinMind API 暫時無法取得財報資料（{e.status_code or '連線失敗'}），請稍後再試"
        )
        return {
            "has_data": False,
            "profile": {}, "profitability": {}, "growth": {}, "shareholder_return": {},
            "checklist": [], "rating": None, "rating_label": "資料不足",
            "module_scores": {
                "growth": None, "profitability": None, "safety": None,
                "base_score": None, "growth_penalty_applied": False,
            },
            "summary": reason,
        }
    valuation = _load_valuation().get(symbol)

    has_data = bool(fs_by_date) or bool(bs_by_date)
    if not has_data:
        return {
            "has_data": False,
            "profile": {}, "profitability": {}, "growth": {}, "shareholder_return": {},
            "checklist": [], "rating": None, "rating_label": "資料不足",
            "module_scores": {
                "growth": None, "profitability": None, "safety": None,
                "base_score": None, "growth_penalty_applied": False,
            },
            "summary": f"查無 {symbol} 的財報資料（可能是 ETF 或非公司證券，FinMind 未提供財報）。",
        }

    fs_quarters = list(fs_by_date.values())
    fs_dates = list(fs_by_date.keys())
    latest_bs = next(iter(reversed(bs_by_date.values())), {})
    latest_cf = next(iter(reversed(cf_by_date.values())), {})

    # 獲利能力
    latest_eps = fs_quarters[-1].get("EPS") if fs_quarters else None
    ttm_eps = _ttm(fs_quarters, "EPS")
    ttm_eps_prior = _ttm(fs_quarters, "EPS", offset=4)
    eps_growth = (
        round((ttm_eps - ttm_eps_prior) / abs(ttm_eps_prior) * 100, 2)
        if ttm_eps is not None and ttm_eps_prior not in (None, 0)
        else None
    )

    latest_revenue = fs_quarters[-1].get("Revenue") if fs_quarters else None
    latest_gross_profit = fs_quarters[-1].get("GrossProfit") if fs_quarters else None
    gross_margin = (
        round(latest_gross_profit / latest_revenue * 100, 2)
        if latest_revenue and latest_gross_profit is not None
        else None
    )
    gross_margin_yoy = None
    if len(fs_quarters) >= 5 and gross_margin is not None:
        prior = fs_quarters[-5]
        prior_rev, prior_gp = prior.get("Revenue"), prior.get("GrossProfit")
        if prior_rev:
            gross_margin_yoy = round(gross_margin - (prior_gp / prior_rev * 100), 2)

    ttm_net_income = _ttm(fs_quarters, "IncomeAfterTaxes")
    equity = latest_bs.get("Equity")
    total_assets = latest_bs.get("TotalAssets")
    roe = round(ttm_net_income / equity * 100, 2) if ttm_net_income is not None and equity else None
    roa = round(ttm_net_income / total_assets * 100, 2) if ttm_net_income is not None and total_assets else None

    # 公司體質
    current_assets, current_liabilities = latest_bs.get("CurrentAssets"), latest_bs.get("CurrentLiabilities")
    current_ratio = (
        round(current_assets / current_liabilities * 100, 2) if current_assets and current_liabilities else None
    )
    debt_ratio = (
        round((total_assets - equity) / total_assets * 100, 2) if total_assets and equity is not None else None
    )

    # 成長能力
    annual_revenue = _annual_revenue_by_year(fs_by_date)
    years = sorted(annual_revenue.keys(), reverse=True)
    revenue_cagr = None
    if len(years) >= 4 and years[0] - years[3] == 3:
        latest_year_rev, base_year_rev = annual_revenue[years[0]], annual_revenue[years[3]]
        if base_year_rev > 0:
            revenue_cagr = round(((latest_year_rev / base_year_rev) ** (1 / 3) - 1) * 100, 2)

    cf_quarters = list(cf_by_date.values())
    ttm_ocf = _ttm(cf_quarters, "CashFlowsFromOperatingActivities")
    ttm_capex = _ttm(cf_quarters, "PropertyAndPlantAndEquipment")
    free_cash_flow = round(ttm_ocf + ttm_capex, 0) if ttm_ocf is not None and ttm_capex is not None else None

    # 股東回報
    dividend_years = sorted({row["year"]: row for row in dividend_rows}.items())
    consecutive_dividend_years = 0
    for _, row in reversed(dividend_years):
        if (row.get("CashEarningsDistribution") or 0) > 0:
            consecutive_dividend_years += 1
        else:
            break

    checklist = [
        {
            "key": "eps_growth", "category": "growth", "label": f"EPS成長率(近四季) > {EPS_GROWTH_MIN:.0f}%",
            "value": eps_growth, "passed": None if eps_growth is None else eps_growth > EPS_GROWTH_MIN,
        },
        {
            "key": "roe", "category": "profitability", "label": f"ROE > {ROE_MIN:.0f}%",
            "value": roe, "passed": None if roe is None else roe > ROE_MIN,
        },
        {
            "key": "revenue_cagr", "category": "growth", "label": f"營收CAGR(近三年) > {REVENUE_CAGR_MIN:.0f}%",
            "value": revenue_cagr, "passed": None if revenue_cagr is None else revenue_cagr > REVENUE_CAGR_MIN,
        },
        {
            "key": "gross_margin_trend", "category": "profitability", "label": "毛利率持平或上升(YoY)",
            "value": gross_margin_yoy,
            "passed": None if gross_margin_yoy is None else gross_margin_yoy >= GROSS_MARGIN_TOLERANCE,
        },
        {
            "key": "debt_ratio", "category": "safety", "label": f"負債比 < {DEBT_RATIO_MAX:.0f}%",
            "value": debt_ratio, "passed": None if debt_ratio is None else debt_ratio < DEBT_RATIO_MAX,
        },
        {
            "key": "free_cash_flow", "category": "safety", "label": "自由現金流為正",
            "value": free_cash_flow, "passed": None if free_cash_flow is None else free_cash_flow > 0,
        },
        {
            "key": "current_ratio", "category": "safety", "label": f"流動比率 > {CURRENT_RATIO_MIN:.0f}%",
            "value": current_ratio, "passed": None if current_ratio is None else current_ratio > CURRENT_RATIO_MIN,
        },
        {
            "key": "dividend_yield", "category": "safety", "label": f"殖利率 > {DIVIDEND_YIELD_MIN:.0f}%",
            "value": valuation.get("dividend_yield") if valuation else None,
            "passed": (
                None if not valuation or valuation.get("dividend_yield") is None
                else valuation["dividend_yield"] > DIVIDEND_YIELD_MIN
            ),
        },
    ]

    evaluable = [c for c in checklist if c["passed"] is not None]

    def _module_score(keys: set[str]) -> float | None:
        items = [c for c in evaluable if c["key"] in keys]
        if not items:
            return None
        return round(100 * sum(1 for c in items if c["passed"]) / len(items), 1)

    growth_score = _module_score(GROWTH_KEYS)
    profitability_score = _module_score(PROFITABILITY_KEYS)
    safety_score = _module_score(SAFETY_KEYS)

    # 若某模組完全沒有可評估的指標（資料缺漏，非「不及格」），排除該模組並依剩餘模組的權重
    # 比例重新分配——「不知道」跟「評估後不及格」是兩種狀態，不該混為一談（同一份資料裡
    # `passed: None` 本來就是特別留給這個用途的第三種狀態）。
    modules = [
        (growth_score, GROWTH_WEIGHT),
        (profitability_score, PROFITABILITY_WEIGHT),
        (safety_score, SAFETY_WEIGHT),
    ]
    available = [(score, weight) for score, weight in modules if score is not None]
    weight_total = sum(weight for _, weight in available)
    base_score = (
        round(sum(score * weight for score, weight in available) / weight_total, 1)
        if weight_total else None
    )

    growth_penalty_applied = growth_score is not None and growth_score < GROWTH_PENALTY_THRESHOLD
    if growth_penalty_applied and base_score is not None:
        base_score = round(base_score * GROWTH_PENALTY_MULTIPLIER, 1)

    # 輸出層轉譯：底層改成 0-100 的基本面基礎分，但對外仍輸出 1.0-5.0 星等，downstream
    # (combined.py 的 _fundamental_tier 門檻、前端 Stars 元件) 完全不用改。
    rating = round(1.0 + base_score / 100 * 4.0, 1) if base_score is not None else None
    rating_label = (
        f"{rating:.1f} / 5.0（成長{growth_score:.0f} 獲利{profitability_score:.0f} 安全{safety_score:.0f}）"
        if rating is not None and None not in (growth_score, profitability_score, safety_score)
        else f"{rating:.1f} / 5.0" if rating is not None else "資料不足"
    )
    if growth_penalty_applied and rating_label != "資料不足":
        rating_label += "（成長動能不足，總分已打8折）"

    if rating is None:
        summary = f"{symbol} 財報資料不足以產生評等。"
    else:
        strengths = [c["label"] for c in evaluable if c["passed"]]
        weaknesses = [c["label"] for c in evaluable if not c["passed"]]
        parts = [f"{symbol} 基本面綜合評等 {rating:.1f}/5.0，{len(evaluable)} 項可評估指標中達標 {len(strengths)} 項。"]
        if strengths:
            parts.append("優勢：" + "、".join(strengths) + "。")
        if weaknesses:
            parts.append("待觀察：" + "、".join(weaknesses) + "。")
        if growth_penalty_applied:
            parts.append("成長動能嚴重不足（成長性模組未達標），總分已強制打8折。")
        summary = "".join(parts)

    return {
        "has_data": True,
        "as_of": fs_dates[-1] if fs_dates else None,
        "profile": {
            "total_assets": total_assets,
            "equity": equity,
            "roe": roe,
            "roa": roa,
            "debt_ratio": debt_ratio,
            "current_ratio": current_ratio,
        },
        "profitability": {
            "eps": latest_eps,
            "eps_ttm": ttm_eps,
            "eps_growth_pct": eps_growth,
            "gross_margin_pct": gross_margin,
            "gross_margin_yoy_pp": gross_margin_yoy,
        },
        "growth": {
            "revenue_cagr_3y_pct": revenue_cagr,
            "free_cash_flow": free_cash_flow,
        },
        "shareholder_return": {
            "dividend_yield_pct": valuation.get("dividend_yield") if valuation else None,
            "pe_ratio": valuation.get("pe_ratio") if valuation else None,
            "pb_ratio": valuation.get("pb_ratio") if valuation else None,
            "consecutive_dividend_years": consecutive_dividend_years,
        },
        "checklist": checklist,
        "rating": rating,
        "rating_label": rating_label,
        "module_scores": {
            "growth": growth_score,
            "profitability": profitability_score,
            "safety": safety_score,
            "base_score": base_score,
            "growth_penalty_applied": growth_penalty_applied,
        },
        "summary": summary,
    }
