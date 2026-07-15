"""技術面 × 基本面綜合判斷引擎 (V3.2 sub-system #4)。

Combines the existing Adaptive Weighted Decision Engine's technical verdict
(`decision.py`) with `fundamentals.py`'s AI基本面評等 into one plain-language
combined verdict — no new scoring model, just a lookup table over two
already-computed results, matching the spec's own example phrasings
("短空長多", "技術與基本面同步轉強，屬高品質布局機會").
"""

FUNDAMENTAL_STRONG_MIN = 3.5
FUNDAMENTAL_WEAK_MAX = 2.5

TECHNICAL_BULLISH = {"buy", "strong_buy"}
TECHNICAL_BEARISH = {"sell", "strong_sell"}

COMBINED_LABELS = {
    ("bullish", "strong"): "技術與基本面同步轉強，屬高品質布局機會",
    ("bullish", "moderate"): "技術轉強，基本面中規中矩，可留意但非最優質標的",
    ("bullish", "weak"): "技術轉強但基本面偏弱，慎防追高後基本面拖累股價",
    ("neutral", "strong"): "基本面體質佳，技術面尚待表態，可留意進場時機",
    ("neutral", "moderate"): "技術與基本面均持平，暫無明顯訊號",
    ("neutral", "weak"): "基本面偏弱，技術面亦無明顯訊號，建議觀望",
    ("bearish", "strong"): "短空長多，基本面體質佳，拉回可能是布局機會",
    ("bearish", "moderate"): "技術轉弱，基本面尚可，短線風險需留意",
    ("bearish", "weak"): "技術與基本面同步轉弱，風險偏高，不宜輕易進場",
}


def _technical_direction(verdict: str) -> str:
    if verdict in TECHNICAL_BULLISH:
        return "bullish"
    if verdict in TECHNICAL_BEARISH:
        return "bearish"
    return "neutral"


def _fundamental_tier(rating: float | None) -> str | None:
    if rating is None:
        return None
    if rating >= FUNDAMENTAL_STRONG_MIN:
        return "strong"
    if rating <= FUNDAMENTAL_WEAK_MAX:
        return "weak"
    return "moderate"


def analyze(decision_result: dict, fundamentals_result: dict) -> dict:
    direction = _technical_direction(decision_result["verdict"])
    rating = fundamentals_result.get("rating")
    tier = _fundamental_tier(rating)

    if tier is None:
        return {
            "combined_label": "基本面資料不足（可能為 ETF 或非公司證券），僅供技術面參考",
            "technical_direction": direction,
            "technical_verdict_label": decision_result["verdict_label"],
            "fundamental_tier": None,
            "has_fundamental_data": False,
        }

    return {
        "combined_label": COMBINED_LABELS[(direction, tier)],
        "technical_direction": direction,
        "technical_verdict_label": decision_result["verdict_label"],
        "fundamental_tier": tier,
        "fundamental_rating": rating,
        "fundamental_rating_label": fundamentals_result["rating_label"],
        "has_fundamental_data": True,
    }
