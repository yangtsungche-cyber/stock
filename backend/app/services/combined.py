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

# 「大趨勢層」——葛蘭碧法則、波浪理論都是判斷中長期趨勢結構的層級，跟乖離率/RSI/籌碼面
# 這類短線、單點的層級性質不同。真正健康的偏多局面，這兩層至少要有一層同向確認；只靠
# 乖離率過大+外資轉買衝分，是「跌深反彈」不是「趨勢轉強」。
TREND_LAYERS = {"granville", "waves"}

# 葛蘭碧法則自己的 8 條規則裡，B4（超跌反彈買點）／S4（超漲回落賣點）本質上是逆勢的乖離率
# 極值反彈訊號——均線仍是空頭排列時一樣能觸發（見 granville.py：B4 唯一條件是乖離率超跌+
# 單日反彈，不像 B1 要求均線方向剛翻轉、B2/B3 要求均線已經在漲），不能拿來當「趨勢層確認」
# 的證據，否則會放過「均線空頭排列下純靠 B4 觸發，卻被判定技術與基本面同步轉強」這種案例
# （2026-07-20 實測 1519 華城：ma_alignment=bearish，葛蘭碧層唯一訊號是 B4，全部 7 個觸發
# 訊號無一例外都是超跌/超買型指標，卻因為葛蘭碧層「有訊號」就被判定趨勢已確認）。
TREND_CONFIRMING_GRANVILLE_CODES = {"B1", "B2", "B2-weak", "B3", "S1", "S2", "S2-weak", "S3"}

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

# 大趨勢層未確認時，偏多文案降級用的保守措辭——只覆蓋 strong/moderate（積極語氣的兩檔），
# weak 那檔本來就已經用「慎防追高」提出警訊，不需要再降級。見 1519 華城案例：KD死亡交叉、
# 葛蘭碧與波浪理論皆中性，純靠均線乖離率+外資轉買衝分，卻被判定「高品質布局機會」——
# 這種純籌碼/短線指標推升的偏多，跟真正趨勢轉強是兩回事。
TREND_UNCONFIRMED_BULLISH_LABEL = "屬跌深後籌碼與技術面初步止穩反彈，大趨勢尚未全面翻多，不宜過度追價"


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


def _trend_confirmed(decision_result: dict, direction: str) -> bool:
    """大趨勢層（葛蘭碧法則／波浪理論）是否至少有一個「真正順勢」的訊號朝這個方向確認——
    避免把純粹靠均線乖離率／籌碼面這種短線訊號堆出的分數，講成語氣積極的「技術轉強」。
    葛蘭碧法則的 B4／S4 本身就是逆勢的超跌/超漲反彈訊號，即使觸發也不算數（見
    TREND_CONFIRMING_GRANVILLE_CODES 上方的說明）；波浪理論沒有這種逆勢訊號，任何同向觸發
    都算數。中性方向不需要趨勢確認（沒有方向性主張可言）。"""
    if direction not in ("bullish", "bearish"):
        return True
    wanted_side = "buy" if direction == "bullish" else "sell"
    for s in decision_result["signals"]:
        if s["layer"] not in TREND_LAYERS or s["side"] != wanted_side:
            continue
        if s["layer"] == "granville" and s["code"] not in TREND_CONFIRMING_GRANVILLE_CODES:
            continue
        return True
    return False


def analyze(decision_result: dict, fundamentals_result: dict) -> dict:
    direction = _technical_direction(decision_result["verdict"])
    rating = fundamentals_result.get("rating")
    tier = _fundamental_tier(rating)

    if tier is None:
        return {
            "combined_label": fundamentals_result.get(
                "summary", "基本面資料不足（可能為 ETF 或非公司證券），僅供技術面參考"
            ),
            "technical_direction": direction,
            "technical_verdict_label": decision_result["verdict_label"],
            "fundamental_tier": None,
            "has_fundamental_data": False,
        }

    label = COMBINED_LABELS[(direction, tier)]
    trend_confirmed = _trend_confirmed(decision_result, direction)
    if direction == "bullish" and tier in ("strong", "moderate") and not trend_confirmed:
        label = TREND_UNCONFIRMED_BULLISH_LABEL

    return {
        "combined_label": label,
        "technical_direction": direction,
        "technical_verdict_label": decision_result["verdict_label"],
        "fundamental_tier": tier,
        "fundamental_rating": rating,
        "fundamental_rating_label": fundamentals_result["rating_label"],
        "has_fundamental_data": True,
        "trend_confirmed": trend_confirmed,
    }
