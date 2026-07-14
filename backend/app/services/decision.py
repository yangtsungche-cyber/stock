"""決策摘要 (Decision Summary): Adaptive Weighted Decision Engine.

Combines every layer's `signals` list (each item already shaped as
`{code, side, label, confidence, reason}` by granville/waves/layers/chips)
into one overall buy/sell verdict.

"Adaptive" = each signal's weight is re-scaled by how well it agrees with the
prevailing MA trend (`granville.ma_alignment`): trend-following signals get a
boost, counter-trend signals get dampened — the same adjustment a
discretionary trader makes when a signal fires with or against the dominant
trend, rather than judging every signal in isolation.
"""

LAYER_WEIGHTS = {
    "granville": 1.0,
    "waves": 0.8,
    "kd": 0.9,
    "macd": 1.0,
    "bias": 0.8,
    "rsi": 0.8,
    "volume": 0.7,
    "margin": 0.8,
    "institutional": 1.1,
}

LAYER_LABELS = {
    "granville": "第一層：葛蘭碧法則",
    "waves": "第二層：波浪理論",
    "kd": "第三層：KD",
    "macd": "第四層：MACD",
    "bias": "第五層：均線乖離率",
    "rsi": "第六層：RSI",
    "volume": "第七層：成交量",
    "margin": "第八層：融資融券",
    "institutional": "第八層：三大法人",
}

TREND_BOOST = 1.15
TREND_DAMPEN = 0.85

# Signals carry confidence on a 0-100 scale (see granville/layers/waves/chips).
# The overall score is normalized against this theoretical "every layer fires
# at maximum confidence, unanimously" ceiling — not against the weight of
# whichever signals happened to fire. Normalizing against the latter collapses
# to a pure direction vote (always ±100 when only one signal exists, no matter
# how weak), which discards both breadth-of-agreement and confidence.
MAX_CONFIDENCE = 100.0

# (score floor, verdict code, verdict label) — first band whose floor the
# score clears, checked from most bullish to most bearish.
VERDICT_BANDS = (
    (40.0, "strong_buy", "強烈偏多"),
    (15.0, "buy", "偏多"),
    (-15.0, "neutral", "中性"),
    (-40.0, "sell", "偏空"),
    (float("-inf"), "strong_sell", "強烈偏空"),
)

TREND_NOTES = {
    "bullish": "均線多頭排列，順勢（買進）訊號權重上修，逆勢（賣出）訊號權重下修",
    "bearish": "均線空頭排列，順勢（賣出）訊號權重上修，逆勢（買進）訊號權重下修",
}


def _verdict(score: float) -> tuple[str, str]:
    for floor, code, label in VERDICT_BANDS:
        if score >= floor:
            return code, label
    return "neutral", "中性"  # unreachable: last band floor is -inf


def _trend_multiplier(side: str, ma_alignment: str) -> float:
    if ma_alignment == "bullish":
        return TREND_BOOST if side == "buy" else TREND_DAMPEN
    if ma_alignment == "bearish":
        return TREND_BOOST if side == "sell" else TREND_DAMPEN
    return 1.0


def analyze(granville_result: dict, waves_result: dict, layers_result: dict, chips_result: dict) -> dict:
    ma_alignment = granville_result.get("ma_alignment", "unknown")

    layer_signals = {
        "granville": granville_result["signals"],
        "waves": waves_result["signals"],
        "kd": layers_result["kd"]["signals"],
        "macd": layers_result["macd"]["signals"],
        "bias": layers_result["bias"]["signals"],
        "rsi": layers_result["rsi"]["signals"],
        "volume": layers_result["volume"]["signals"],
        "margin": chips_result["margin"]["signals"],
        "institutional": chips_result["institutional"]["signals"],
    }

    tagged: list[dict] = []
    layer_breakdown: list[dict] = []
    raw_total = 0.0
    max_possible_weight = sum(LAYER_WEIGHTS.values()) * MAX_CONFIDENCE

    for layer, signals in layer_signals.items():
        layer_weight = LAYER_WEIGHTS[layer]
        layer_raw = 0.0
        layer_denom = 0.0
        for s in signals:
            mult = _trend_multiplier(s["side"], ma_alignment)
            weight = s["confidence"] * layer_weight * mult
            signed = weight if s["side"] == "buy" else -weight
            raw_total += signed
            layer_raw += signed
            layer_denom += weight
            tagged.append({**s, "layer": layer, "contribution": round(signed, 1)})

        layer_breakdown.append({
            "layer": layer,
            "label": LAYER_LABELS[layer],
            "weight": layer_weight,
            "signal_count": len(signals),
            "score": round(100 * layer_raw / layer_denom, 1) if layer_denom else 0.0,
        })

    raw_score = 100 * raw_total / max_possible_weight if max_possible_weight else 0.0
    score = round(max(-100.0, min(100.0, raw_score)), 1)
    verdict, verdict_label = _verdict(score)
    tagged.sort(key=lambda s: -abs(s["contribution"]))

    return {
        "score": score,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "trend_context": {
            "ma_alignment": ma_alignment,
            "note": TREND_NOTES.get(ma_alignment, "均線排列不明確，各訊號權重維持基準值"),
        },
        "layer_breakdown": layer_breakdown,
        "signals": tagged,
    }
