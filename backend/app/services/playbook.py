"""Investment Playbook: rule-based entry/exit levels, position sizing, and
invalidation conditions derived from the decision engine's verdict.

Same philosophy as every other module here — plain deterministic rules over
already-computed data (no LLM call), so the whole site stays consistent and
explainable. Support/resistance reuse `waves.py`'s ZigZag pivots. The
stop-loss/entry-zone buffer is *derived from* (not equal to) `waves.py`'s
ATR-scaled `threshold_pct` — that threshold is deliberately wide (ATR x3.5,
floored at 5%) because its job is filtering noise for wave-pivot detection,
not sizing a protective stop. Used unscaled it produced buffers of 8-10%+
(more than a single day's limit-up/down), so it's scaled down and capped
into a realistic stop-loss range instead.
"""

BUY_SCORE_FLOOR = 15.0
SELL_SCORE_CEIL = -15.0

SIZING_HIGH_FLOOR = 40.0
SIZING_MEDIUM_FLOOR = 15.0
MIN_RISK_REWARD = 1.5

# Stop-loss/entry-zone buffer: a fraction of the (much wider) ZigZag swing
# threshold, capped to a realistic protective-stop distance.
STOP_BUFFER_FLOOR = 0.02
STOP_BUFFER_CEIL = 0.05
STOP_BUFFER_SCALE = 0.4

# V3.4：「觀望」不再是一句固定文字——依收盤價與支撐/壓力的相對距離（±3%）動態帶出對應劇本。
NEAR_LEVEL_THRESHOLD = 0.03

DISCLAIMER = (
    "以上價位與部位建議皆由歷史價量資料以固定規則運算而成，用於輔助決策品質，"
    "並非個股價格預測，亦不構成投資建議。過去績效不代表未來表現，資料可能存在延遲，"
    "投資人應自行評估風險，並留意個別券商之交易成本與規範。"
)


def _support(close: float, ma20: float | None, ma60: float | None, pivots: list[dict]) -> float:
    below = [p["price"] for p in pivots if p["type"] == "L" and p["price"] < close]
    if below:
        return max(below)  # nearest support below current price
    for level in (ma20, ma60):
        if level is not None and level < close:
            return level
    return round(close * 0.95, 2)


def _resistance(close: float, ma20: float | None, pivots: list[dict]) -> float | None:
    above = [p["price"] for p in pivots if p["type"] == "H" and p["price"] > close]
    if above:
        return min(above)  # nearest resistance above current price
    if ma20 is not None and ma20 > close:
        return ma20
    return None


def _buffer_pct(threshold_pct: float) -> float:
    return min(STOP_BUFFER_CEIL, max(STOP_BUFFER_FLOOR, threshold_pct * STOP_BUFFER_SCALE))


def _position_sizing(stance: str, score: float, risk_reward: float | None) -> dict:
    if stance == "neutral":
        return {
            "tier": "none",
            "label": "觀望",
            "note": "訊號分歧或強度不足，建議暫不進場，持續觀察訊號明細的變化。",
        }

    abs_score = abs(score)

    if stance == "buy":
        if abs_score >= SIZING_HIGH_FLOOR:
            tier, label = "high", "較高部位"
            note = "多層訊號高度一致，可考慮較高部位（例如核心部位上限的 70-100%），仍建議分批布局並嚴設停損。"
        elif abs_score >= SIZING_MEDIUM_FLOOR:
            tier, label = "medium", "中等部位"
            note = "訊號方向明確但強度中等，建議中等部位（40-70%）分批布局。"
        else:
            tier, label = "low", "小額試單"
            note = "訊號強度偏弱，建議以小部位（30% 以下）試單或持續觀察。"

        if risk_reward is not None and risk_reward < MIN_RISK_REWARD:
            tier, label = "low", "小額試單（風報比偏低）"
            note = (
                f"風險報酬比約 {risk_reward:.2f}，低於建議門檻 {MIN_RISK_REWARD:.1f}，"
                "即使訊號方向明確，仍建議降低部位或等待更佳進場點。"
            )
    else:  # sell
        if abs_score >= SIZING_HIGH_FLOOR:
            tier, label = "high", "建議積極減碼"
            note = "多層訊號高度一致偏空，若持有部位可考慮較大幅度減碼或出清（例如 70-100%），並嚴設防守價。"
        elif abs_score >= SIZING_MEDIUM_FLOOR:
            tier, label = "medium", "建議部分減碼"
            note = "訊號方向偏空但強度中等，可考慮減碼 40-70%，其餘部位嚴設防守價。"
        else:
            tier, label = "low", "小幅減碼／觀察"
            note = "空方訊號強度偏弱，可考慮小幅減碼（30% 以下）或持續觀察，非急迫出場訊號。"

    return {"tier": tier, "label": label, "note": note}


def _invalidation(
    stance: str,
    stop_loss: float | None,
    resistance: float | None,
    ma_alignment: str,
    institutional_streak: dict,
) -> list[str]:
    conditions: list[str] = []

    if stance == "buy":
        if stop_loss is not None:
            conditions.append(f"若收盤價跌破 {stop_loss:.2f}，多方操作論點失效，應執行停損")
        if ma_alignment == "bullish":
            conditions.append("若均線由多頭排列（20>60>120）轉為空頭或交錯排列，趨勢結構轉弱，須重新評估")
        if institutional_streak.get("direction") == "up":
            conditions.append("若三大法人由連續買超轉為連續賣超，籌碼面轉弱，觀點須重新檢視")
    elif stance == "sell":
        # Invalidating a bearish view means price reclaims resistance, not merely
        # staying above the downside protective stop (which it always trivially is).
        if resistance is not None:
            conditions.append(f"若收盤價站穩壓力 {resistance:.2f} 之上，空方／減碼論點失效，可重新評估多方機會")
        if ma_alignment == "bearish":
            conditions.append("若均線由空頭排列（20<60<120）轉為多頭或交錯排列，趨勢結構轉強，須重新評估")
        if institutional_streak.get("direction") == "down":
            conditions.append("若三大法人由連續賣超轉為連續買超，籌碼面轉強，觀點須重新檢視")
    else:
        conditions.append("若綜合分數上升至 +15 以上，可留意偏多操作機會")
        conditions.append("若綜合分數下降至 -15 以下，則留意偏空或減碼時機")

    return conditions


def analyze(ind: dict, granville_result: dict, waves_result: dict, chips_result: dict, decision_result: dict) -> dict:
    close = ind["close"][-1]
    ma20 = ind["ma"]["20"][-1]
    ma60 = ind["ma"]["60"][-1]
    pivots = waves_result["pivots"]
    threshold_pct = waves_result["threshold_pct"]
    ma_alignment = granville_result.get("ma_alignment", "unknown")
    institutional_streak = chips_result["institutional"].get("streak", {"direction": None, "days": 0})
    score = decision_result["score"]

    if close is None:
        return {
            "stance": "neutral",
            "stance_label": "資料不足",
            "action_note": "價格資料不足，暫無法產生進出場建議。",
            "reference_levels": {"close": None, "support": None, "resistance": None},
            "entry_zone": None,
            "stop_loss": None,
            "stop_loss_note": None,
            "target": None,
            "risk_reward_ratio": None,
            "position_sizing": {"tier": "none", "label": "觀望", "note": "資料不足。"},
            "invalidation": [],
            "disclaimer": DISCLAIMER,
        }

    support = _support(close, ma20, ma60, pivots)
    resistance = _resistance(close, ma20, pivots)
    buffer_pct = _buffer_pct(threshold_pct)

    if score >= BUY_SCORE_FLOOR:
        stance, stance_label = "buy", "偏多操作"
        action_note = "訊號整體偏多，可留意拉回支撐附近的分批進場機會。"

        entry_low = round(support, 2)
        entry_high = round(support * (1 + buffer_pct), 2)
        stop_loss = round(support * (1 - buffer_pct), 2)
        stop_note = f"跌破支撐 {support:.2f} 並拉開 {buffer_pct * 100:.1f}% 視為進場論點失效"

        risk = entry_high - stop_loss
        if resistance is not None and resistance > entry_high:
            target = round(resistance, 2)
        else:
            target = round(entry_high + risk * 2, 2)
        risk_reward = round((target - entry_high) / risk, 2) if risk > 0 else None

        entry_zone = {"low": entry_low, "high": entry_high}

    elif score <= SELL_SCORE_CEIL:
        stance, stance_label = "sell", "偏空／建議減碼"
        action_note = "訊號整體偏空，非新進場買點；若已持有部位，建議留意防守價與逢高調節。"

        entry_zone = None
        stop_loss = round(support * (1 - buffer_pct), 2)
        stop_note = f"若已持有部位，跌破 {stop_loss:.2f}（支撐 {support:.2f} 下緣）建議停損／減碼"
        target = round(resistance, 2) if resistance is not None else None
        risk_reward = None

    else:
        stance, stance_label = "neutral", "觀望"
        entry_zone = None
        stop_loss = None
        stop_note = None
        target = None
        risk_reward = None

        # 支撐(support)一定有值（_support 最差也有 close*0.95 的保底），但壓力(resistance)
        # 找不到明確前高/MA20 時會是 None——「接近支撐」永遠可以判斷，「接近壓力」跟「區間
        # 震盪」都要先確認 resistance 存在，否則退化成只講支撐的版本。
        near_support = (close - support) / close <= NEAR_LEVEL_THRESHOLD
        near_resistance = resistance is not None and (resistance - close) / close <= NEAR_LEVEL_THRESHOLD

        if near_support:
            action_note = (
                f"觀望：目前股價（{close:.2f}）已接近支撐位 {support:.2f}，短線跌幅趨緩。"
                "建議暫不盲目追殺，靜待支撐位守穩並出現技術面打底訊號（如 KD 黃金交叉或量縮止跌）後，"
                "再行考慮分批試單。"
            )
        elif near_resistance:
            action_note = (
                f"觀望：目前股價（{close:.2f}）已逼近壓力位 {resistance:.2f}，面臨前高反彈或解套賣壓。"
                "此處不宜過度追高，操作建議維持觀望，待股價帶量突破壓力位或回檔測試支撐不破後，再行追蹤。"
            )
        elif resistance is not None:
            action_note = (
                f"觀望：目前股價（{close:.2f}）於支撐位 {support:.2f} 與壓力位 {resistance:.2f} 之間狹幅震盪，"
                "多空訊號方向分歧且動能不足。操作建議靜待方向突破區間後，再依新訊號順勢布局。"
            )
        else:
            action_note = (
                f"觀望：目前股價（{close:.2f}）距支撐位 {support:.2f} 尚有一段距離，且暫無明確壓力參考價位，"
                "多空訊號方向分歧且動能不足。操作建議靜待方向明確後再依新訊號順勢布局。"
            )

    sizing = _position_sizing(stance, score, risk_reward)
    invalidation = _invalidation(stance, stop_loss, resistance, ma_alignment, institutional_streak)

    return {
        "stance": stance,
        "stance_label": stance_label,
        "action_note": action_note,
        "reference_levels": {
            "close": round(close, 2),
            "support": round(support, 2),
            "resistance": round(resistance, 2) if resistance is not None else None,
        },
        "entry_zone": entry_zone,
        "stop_loss": stop_loss,
        "stop_loss_note": stop_note,
        "target": target,
        "risk_reward_ratio": risk_reward,
        "position_sizing": sizing,
        "invalidation": invalidation,
        "disclaimer": DISCLAIMER,
    }
