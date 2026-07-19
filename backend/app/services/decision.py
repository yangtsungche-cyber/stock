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

# V3.2：訊號強度顆粒度分級——訊號不再一律用同一套信心度硬湊分數，改成「這個型態本身的
# 動能等級（強度基數）」乘上「這個分級的固定信心度」。兩者是獨立維度：強度基數表達型態
# 統計上的動能爆發力，信心度表達這個分級整體的可信程度；各訊號實際落點見
# granville.py/layers.py/waves.py/chips.py 各自訊號定義裡的 "tier" 欄位。
STRENGTH_BASE = {"strong": 100.0, "medium": 60.0, "weak": 30.0}
TIER_CONFIDENCE = {"strong": 70.0, "medium": 50.0, "weak": 40.0}

# 每個分級「單一訊號」能拿到的最大值（強度基數 × 信心度，未乘 layer_weight/trend）——
# 用來算動態天花板，不用每次重新掃過訊號定義。
TIER_MAX_VALUE = {tier: STRENGTH_BASE[tier] * TIER_CONFIDENCE[tier] / 100.0 for tier in STRENGTH_BASE}
# => {"strong": 70.0, "medium": 30.0, "weak": 12.0}

# 每一層「理論上可能觸發的最高分級」，由該層目前定義的訊號集合決定：
#   granville: B1/S1 為 strong（其餘 B2-B4/S2-S4 皆 medium/weak）
#   waves:     W5/W3 為 strong（WC 為 weak，無 medium 訊號）
#   kd:        K3/K4（超買超賣）為 medium 是本層最高（K1/K2 交叉為 weak）
#   macd:      D3/D4（零軸突破）為 strong（D1/D2 黃金死亡交叉為 medium）
#   bias:      全部訊號皆為 weak
#   rsi:       R1/R2（超買超賣）為 medium 是本層最高（R3/R4 交叉為 weak）
#   volume:    V1/V2（量價同向確認）為 medium 是本層最高（V3/V4 背離為 weak）
#   margin:    全部訊號皆為 medium
#   institutional: I1-I4 為 medium 是本層最高（I5/I6 單日轉向為 weak）
# 若未來新增/調整某層訊號的分級，這裡要同步更新，否則天花板會失準。
LAYER_MAX_TIER = {
    "granville": "strong",
    "waves": "strong",
    "kd": "medium",
    "macd": "strong",
    "bias": "weak",
    "rsi": "medium",
    "volume": "medium",
    "margin": "medium",
    "institutional": "medium",
}

# 覆蓋率封頂：即使分數算出來夠高，訊號基礎太窄（例如只有均線乖離率+籌碼面兩三層觸發，
# 趨勢層/動能層完全沒表態）就不該喊出偏多/偏空——這是決策等級的硬性限制，不是把分數再打
# 折。分數本身已經用「每層都以自己最高分級順勢觸發」當固定分母正規化過一次（見下方
# max_possible_weight 的算法），覆蓋率越低分數天花板本來就越低；若再把分數乘以覆蓋率折
# 扣，等於雙重懲罰、扭曲分數本身
# （未來要拿分數做歷史回測時，被扭曲過的分數會讓回測邏輯混亂）。改成只封頂「決策等級」，
# 分數維持不變，兩者關注點分開——分數給後續回測用，決策等級才是要不要行動的門檻。
# 門檻與真實案例對照：6197 佳必琪 33.3% 覆蓋率、2472 立隆電 33.3%，皆低於此門檻應封頂；
# 1519 華城 55.6% 覆蓋率則高於門檻，不受此規則影響（但已透過 combined.py 的趨勢層確認
# 規則另外處理其「跌深反彈被誤判為高品質布局」的問題）。
COVERAGE_CAP_THRESHOLD = 40.0

# A/B/C/D 訊號品質分級：只在決策等級為偏多/偏空（封頂後）時才有意義——中性（無論是本來
# 就中性，還是被覆蓋率封頂降級）一律 D 級，代表「系統不建議把這當成方向性訊號」。
GRADE_A_MIN_COVERAGE = 70.0
GRADE_B_MIN_COVERAGE = 50.0
GRADE_C_MIN_COVERAGE = COVERAGE_CAP_THRESHOLD

# 總分正規化的分母是「每一層都以自己最高分級、且順勢（拿到 TREND_BOOST）觸發」這個理論
# 天花板（見 analyze() 內 max_possible_weight 的算法）——不是用實際觸發訊號的權重總和來
# 歸一化。用後者會退化成純方向投票（只要有一個訊號，不論多弱都會拉到 ±100），同時丟失
# 「訊號廣度」與「訊號分級強弱」這兩個維度。

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


def _grade(verdict: str, coverage_pct: float) -> str:
    if verdict == "neutral":
        return "D"
    if coverage_pct >= GRADE_A_MIN_COVERAGE:
        return "A"
    if coverage_pct >= GRADE_B_MIN_COVERAGE:
        return "B"
    return "C"  # verdict is directional here only when coverage already cleared COVERAGE_CAP_THRESHOLD


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

    # Whether each layer actually had data to evaluate, as opposed to having
    # data but finding no signal ("有資料，中性" vs "無資料，系統不知道" — these
    # must not collapse into the same "0 訊號" reading). Price-derived layers
    # (granville/kd/macd/bias/rsi/volume) always have data if the request got
    # this far; margin/institutional can be data-less for TPEx-only symbols or
    # a fetch miss ([[stock-project-step-progress]] fix #3); waves reports its
    # own "insufficient_data" pattern when too few pivots were found.
    layer_has_data = {
        "granville": True,
        "waves": waves_result.get("pattern") != "insufficient_data",
        "kd": True,
        "macd": True,
        "bias": True,
        "rsi": True,
        "volume": True,
        "margin": chips_result["margin"].get("has_data", True),
        "institutional": chips_result["institutional"].get("has_data", True),
    }

    tagged: list[dict] = []
    layer_breakdown: list[dict] = []
    raw_total = 0.0
    # 每層以「自己最高分級 × 順勢加成」為理論天花板，再依 layer_weight 加總——見
    # LAYER_MAX_TIER/TIER_MAX_VALUE 上方的說明與各層訊號定義的 tier 標註。
    max_possible_weight = sum(
        TIER_MAX_VALUE[LAYER_MAX_TIER[layer]] * layer_weight
        for layer, layer_weight in LAYER_WEIGHTS.items()
    ) * TREND_BOOST

    for layer, signals in layer_signals.items():
        layer_weight = LAYER_WEIGHTS[layer]
        layer_raw = 0.0
        layer_denom = 0.0
        for s in signals:
            mult = _trend_multiplier(s["side"], ma_alignment)
            strength = STRENGTH_BASE[s["tier"]]
            weight = strength * (s["confidence"] / 100.0) * layer_weight * mult
            signed = weight if s["side"] == "buy" else -weight
            raw_total += signed
            layer_raw += signed
            layer_denom += weight
            tagged.append({**s, "layer": layer, "contribution": round(signed, 1)})

        has_data = layer_has_data[layer]
        status = "no_data" if not has_data else ("fired" if signals else "neutral")

        layer_breakdown.append({
            "layer": layer,
            "label": LAYER_LABELS[layer],
            "weight": layer_weight,
            "signal_count": len(signals),
            "score": round(100 * layer_raw / layer_denom, 1) if layer_denom else 0.0,
            "status": status,
        })

    raw_score = 100 * raw_total / max_possible_weight if max_possible_weight else 0.0
    score = round(max(-100.0, min(100.0, raw_score)), 1)
    raw_verdict, raw_verdict_label = _verdict(score)
    tagged.sort(key=lambda s: -abs(s["contribution"]))

    layers_total = len(LAYER_WEIGHTS)
    layers_with_data = sum(1 for v in layer_has_data.values() if v)
    layers_fired = sum(1 for b in layer_breakdown if b["status"] == "fired")
    coverage_pct = round(100 * layers_fired / layers_with_data, 1) if layers_with_data else 0.0
    coverage = {
        "layers_total": layers_total,
        "layers_with_data": layers_with_data,
        "layers_fired": layers_fired,
        "coverage_pct": coverage_pct,
        "no_data_layers": [LAYER_LABELS[l] for l, v in layer_has_data.items() if not v],
    }

    # 分數本身不變（回測需要真實、未扭曲的分數）；只有「決策等級」在訊號基礎太窄時被封頂
    # 降為中性——分數與行動門檻，兩件事分開處理。
    verdict_capped = raw_verdict != "neutral" and coverage_pct < COVERAGE_CAP_THRESHOLD
    verdict, verdict_label = ("neutral", "中性") if verdict_capped else (raw_verdict, raw_verdict_label)
    grade = _grade(verdict, coverage_pct)

    return {
        "score": score,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "grade": grade,
        "raw_verdict": raw_verdict,
        "verdict_capped": verdict_capped,
        "trend_context": {
            "ma_alignment": ma_alignment,
            "note": TREND_NOTES.get(ma_alignment, "均線排列不明確，各訊號權重維持基準值"),
        },
        "coverage": coverage,
        "layer_breakdown": layer_breakdown,
        "signals": tagged,
    }
