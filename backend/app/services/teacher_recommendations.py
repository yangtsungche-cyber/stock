"""老師建議清單——技術面/基本面交叉比對 + 三家 AI（ChatGPT/Gemini/Claude）綜合評判排名。

跟 `combined.py`/`decision.py` 一樣，這裡刻意不直接呼叫任何付費 LLM API（沿用持股匯入那次
討論定案的原則：使用者自己去外部問 ChatGPT/Gemini/Claude，把回答貼進來，這支只做「規則式」
文字解析 + 整合，不是又一次 LLM 呼叫）。三家意見的整合、跟這裡的「系統排名」怎麼算，見
`reconcile_round`/`compute_ranking` 的說明。
"""

import re
from datetime import datetime, timezone

from app.models import TeacherRecommendation
from app.services import scan

PROVIDERS = ("chatgpt", "claude", "gemini")
RECONCILED_FIELDS = (
    "main_industry", "long_term_rating", "investment_category",
    "ai_benefit_rating", "volatility", "suitable_strategy",
)
# ChatGPT > Claude > Gemini 平手時的優先順序——ChatGPT 是這份清單最初的資料來源（使用者已經
# 看過、認可過的版本），三家真的意見分歧、又沒有多數共識時，以它為錨點最合理。
_TIE_BREAK_ORDER = ("chatgpt", "claude", "gemini")

VOLATILITY_VALUES = ("高", "中高", "中", "中低", "低")
STRATEGY_VALUES = ("波段", "長抱", "短線", "觀察")
_SYNONYMS = {
    "中等": "中",
    "普通": "中",
    "高波動": "高",
    "低波動": "低",
    "波段操作": "波段",
    "長期持有": "長抱",
    "長期": "長抱",
    "短期": "短線",
    "短波": "短線",
    "觀望": "觀察",
}

PROMPT_TEMPLATE = """\
請針對以下 {count} 檔台股，逐一給出評估，「務必」每檔輸出剛好一行，格式固定為：
代號|主要產業|長期評價(0-5,可小數.5)|投資分類|AI受惠程度(0-5,可小數.5)|波動程度(高/中高/中/中低/低)|適合策略(波段/長抱/短線/觀察)

長期評價、AI受惠程度請用數字（例如 4 或 4.5），不要用星號。
波動程度只能是「高/中高/中/中低/低」其中一個；適合策略只能是「波段/長抱/短線/觀察」其中一個。
不要輸出任何其他文字、標題、程式碼區塊、項目符號或說明——剛好 {count} 行，一行一檔，順序不拘。

股票清單：
{symbol_lines}"""


def build_prompt(rows: list[TeacherRecommendation]) -> str:
    symbol_lines = "\n".join(f"{r.symbol} {r.name}" for r in rows)
    return PROMPT_TEMPLATE.format(count=len(rows), symbol_lines=symbol_lines)


def _normalize(value: str) -> str:
    value = re.sub(r"\s+", "", value.strip())
    # 全形轉半形常見標點，避免同一個值因為全半形不同被當成兩種答案
    table = str.maketrans("，。：；！？（）", ",.:;!?()")
    return value.translate(table)


def _match_controlled_vocab(raw: str, allowed: tuple[str, ...]) -> tuple[str, bool]:
    """回傳 (值, 是否為可辨識的合法值)。"""
    norm = _normalize(raw)
    norm = _SYNONYMS.get(norm, norm)
    if norm in allowed:
        return norm, True
    return raw.strip(), False


def _extract_rating(raw: str) -> float | None:
    match = re.search(r"\d+(\.\d+)?", raw)
    if match:
        value = float(match.group())
    elif "★" in raw:
        value = float(raw.count("★"))
    else:
        return None
    return round(max(0.0, min(5.0, value)) * 2) / 2


def parse_provider_reply(provider: str, text: str, expected_symbols: set[str]) -> dict:
    """規則式解析（不是 LLM 呼叫）——鏡射 `portfolio.parse_paste` 容錯/收集錯誤的做法，
    但這裡格式是 pipe-分隔且沒有標題列（提示詞本身就要求 AI 不要輸出標題）。
    """
    rows: list[dict] = []
    errors: list[str] = []
    seen_symbols: set[str] = set()

    cleaned = re.sub(r"^```.*$", "", text, flags=re.MULTILINE)
    for lineno, raw_line in enumerate(cleaned.strip().splitlines(), start=1):
        line = raw_line.strip().strip("`").strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            errors.append(f"第 {lineno} 行：欄位數不對（需要 7 個以「|」分隔的欄位）：{line}")
            continue

        symbol_raw, industry, long_term_raw, category, ai_benefit_raw, volatility_raw, strategy_raw = parts
        symbol = symbol_raw.strip().upper()
        if symbol not in expected_symbols:
            errors.append(f"第 {lineno} 行：股票代號 '{symbol}' 不在目前清單中，已略過")
            continue

        volatility, volatility_ok = _match_controlled_vocab(volatility_raw, VOLATILITY_VALUES)
        strategy, strategy_ok = _match_controlled_vocab(strategy_raw, STRATEGY_VALUES)

        rows.append({
            "symbol": symbol,
            "main_industry": industry.strip() or None,
            "long_term_rating": _extract_rating(long_term_raw),
            "investment_category": category.strip() or None,
            "ai_benefit_rating": _extract_rating(ai_benefit_raw),
            "volatility": volatility or None,
            "suitable_strategy": strategy or None,
            "unrecognized": not (volatility_ok and strategy_ok),
        })
        seen_symbols.add(symbol)

    missing_symbols = sorted(expected_symbols - seen_symbols)
    return {"provider": provider, "rows": rows, "errors": errors, "missing_symbols": missing_symbols}


def _reconcile_numeric(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present) * 2) / 2


def _reconcile_categorical(values_by_provider: dict[str, str | None]) -> str | None:
    ordered = [values_by_provider.get(p) for p in _TIE_BREAK_ORDER]
    present = [(orig, _normalize(orig)) for orig in ordered if orig]
    if not present:
        return None

    counts: dict[str, int] = {}
    for _, norm in present:
        counts[norm] = counts.get(norm, 0) + 1
    winner_norm = max(counts, key=lambda k: counts[k])
    if counts[winner_norm] >= 2:
        for orig, norm in present:
            if norm == winner_norm:
                return orig
    return present[0][0]  # 全部三家不同或只有一家回答 -> 依優先順序取第一個有回答的


def reconcile_round(
    existing: TeacherRecommendation, parsed_by_provider: dict[str, dict[str, str | float | None] | None]
) -> dict:
    """`parsed_by_provider` = {"chatgpt": {...} | None, "claude": {...} | None, "gemini": {...} | None}
    每個非 None 值是 `parse_provider_reply` 那一行 parse 出來、屬於這檔股票的欄位 dict。

    數值欄位：有回答的取平均；三家都沒回答 -> 保留資料庫原值不動（這次重新整理可能只涵蓋
    部分股票）。分類欄位同理，多數決 + tie-break，全部缺席一樣保留原值。
    """
    numeric_fields = ("long_term_rating", "ai_benefit_rating")
    categorical_fields = ("main_industry", "investment_category", "volatility", "suitable_strategy")

    result: dict = {}
    any_provider_answered = any(v is not None for v in parsed_by_provider.values())

    for field in numeric_fields:
        values = [v[field] for v in parsed_by_provider.values() if v is not None]
        reconciled = _reconcile_numeric(values)
        result[field] = reconciled if reconciled is not None else getattr(existing, field)

    for field in categorical_fields:
        values_by_provider = {p: (v[field] if v is not None else None) for p, v in parsed_by_provider.items()}
        reconciled = _reconcile_categorical(values_by_provider)
        result[field] = reconciled if reconciled is not None else getattr(existing, field)

    result["updated_at"] = datetime.now(timezone.utc) if any_provider_answered else existing.updated_at
    return result


def compute_changes(rows: list[TeacherRecommendation], parsed: dict[str, dict | None]) -> list[dict]:
    """`parsed` = {"chatgpt": parse_provider_reply(...)|None, "claude": ..., "gemini": ...} —
    `None` for any provider the user didn't paste text for this round. 只回傳「至少一家有回答」
    的股票（沒人提到的股票這次不動，見 `reconcile_round`），供 /refresh/parse 預覽跟
    /refresh/save 寫入共用同一份計算。
    """
    rows_by_symbol: dict[str, dict[str, dict]] = {}
    for provider, result in parsed.items():
        if result is None:
            continue
        for parsed_row in result["rows"]:
            rows_by_symbol.setdefault(parsed_row["symbol"], {})[provider] = parsed_row

    changes: list[dict] = []
    for row in rows:
        provider_rows = rows_by_symbol.get(row.symbol)
        if not provider_rows:
            continue
        parsed_by_provider = {p: provider_rows.get(p) for p in PROVIDERS}
        reconciled = reconcile_round(row, parsed_by_provider)
        changes.append({
            "id": row.id,
            "symbol": row.symbol,
            "name": row.name,
            "current": {f: getattr(row, f) for f in RECONCILED_FIELDS},
            "reconciled": {f: reconciled[f] for f in RECONCILED_FIELDS},
            "sources": {p: provider_rows.get(p) for p in PROVIDERS},
            "unrecognized": any(v.get("unrecognized") for v in provider_rows.values()),
        })
    return changes


# 品質分數 (0-100, 以 2.5 星為中心) 跟 technical_score (-100..100) 的混合權重——技術面主導
# (0.6)，因為使用者明確把這個新排名定位成「進場時機」視角，AI 綜合評判的品質星等只是次要
# 調整項；兩項權重加總為 1，混合後仍落在 -100..100，前端可以直接沿用既有的紅=偏多/
# 綠=偏空色階，不用另外設計一套配色。
TECHNICAL_WEIGHT = 0.6
QUALITY_WEIGHT = 0.4


def _compute_composite(technical_score: float, long_term_rating: float | None, ai_benefit_rating: float | None) -> tuple[float, bool]:
    stars = [s for s in (long_term_rating, ai_benefit_rating) if s is not None]
    if not stars:
        return technical_score, False
    quality_stars = sum(stars) / len(stars)
    quality_signed = (quality_stars - 2.5) / 2.5 * 100
    composite = TECHNICAL_WEIGHT * technical_score + QUALITY_WEIGHT * quality_signed
    return round(composite, 1), True


async def build_dashboard(rows: list[TeacherRecommendation]) -> list[dict]:
    if not rows:
        return []

    symbols = [r.symbol for r in rows]
    scan_results = await scan.run_scan([], [], symbols_override=symbols)
    results_by_symbol = {r["symbol"]: r for r in scan_results}

    dashboard: list[dict] = []
    for row in rows:
        base = {
            "id": row.id,
            "symbol": row.symbol,
            "name": row.name,
            "teacher_rank": row.teacher_rank,
            "main_industry": row.main_industry,
            "long_term_rating": row.long_term_rating,
            "investment_category": row.investment_category,
            "ai_benefit_rating": row.ai_benefit_rating,
            "volatility": row.volatility,
            "suitable_strategy": row.suitable_strategy,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

        scan_result = results_by_symbol.get(row.symbol)
        if not scan_result or scan_result.get("error"):
            dashboard.append({
                **base,
                "error": (scan_result or {}).get("error", "無法取得分析結果"),
                "composite_score": float("-inf"),
                "quality_available": row.long_term_rating is not None or row.ai_benefit_rating is not None,
            })
            continue

        composite_score, quality_available = _compute_composite(
            scan_result["technical_score"], row.long_term_rating, row.ai_benefit_rating
        )

        dashboard.append({
            **base,
            "close": scan_result["close"],
            "technical_score": scan_result["technical_score"],
            "technical_verdict": scan_result["technical_verdict"],
            "technical_verdict_label": scan_result["technical_verdict_label"],
            "grade": scan_result["grade"],
            "confidence_pct": scan_result["confidence_pct"],
            "fundamental_rating": scan_result["fundamental_rating"],
            "fundamental_rating_label": scan_result["fundamental_rating_label"],
            "combined_label": scan_result["combined_label"],
            "composite_score": composite_score,
            "quality_available": quality_available,
        })

    dashboard.sort(key=lambda d: d["composite_score"], reverse=True)
    for i, d in enumerate(dashboard, start=1):
        d["system_rank"] = i if d["composite_score"] != float("-inf") else None
        if d["composite_score"] == float("-inf"):
            d["composite_score"] = None

    return dashboard
