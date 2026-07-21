"""Position Risk Score axis — 現在的位置是「漲多／跌深」到什麼程度，跟 decision.py 的
方向分數是兩個不同的問題。方向分數答的是「該不該偏多/偏空」，這一支答的是「現在追價是
不是追在高點」（ChatGPT 對 00713 的診斷：22.5 分「偏多」跟「五波疑似完成＋長天期乖離過
大」兩件事被混在同一個分數裡，導致使用者誤判成可以追價）。

刻意直接重用 decision.py 已經算好、已經 tag 過 layer/code 的 `signals` list，不重新讀
granville/waves/layers 的原始資料——這幾個訊號代碼本來就已經存在、已經在跑，只是被歸類
成「方向」訊號的一部分。這裡只是把其中「本質上在講位置，不是在講方向」的幾顆（五波完成、
ABC修正完成、20/60/120/240日乖離過大、價漲量縮/價跌量縮、RSI超買超賣）另外加總一次。

跟 decision.py 的分數刻意不共用同一套正規化：decision.py 的分數會被 backtest_engine.py
拿去做訊號指紋回測，那邊的加總邏輯是凍結的，不能為了這支新指標去動它；這裡訊號數量少、
量級固定，直接 clamp 到 ±100 即可，先驗證分數是否合理，之後若要正式上線再考慮要不要對齊。
"""

# code -> 這個訊號在「位置軸」上的權重，不分方向；方向看訊號自己的 side：
# side == "buy"（超跌/築底類）記正分（低檔，機會）；side == "sell"（超漲/築頂類）記負分（高檔，風險）。
POSITION_SIGNAL_WEIGHTS = {
    "W5": 30, "W5-down": 30,               # 五波完成疑似反轉（waves.py）
    "WC": 20,                               # ABC 修正完成（waves.py）
    "S4": 15, "B4": 15,                     # 20日乖離過熱/超跌（granville.py）
    "BI60-high": 10, "BI60-low": 10,
    "BI120-high": 20, "BI120-low": 20,
    "BI240-high": 20, "BI240-low": 20,      # 長天期乖離過大（layers.py::analyze_bias）
    "V3": 15, "V4": 10,                     # 價漲量縮／價跌量縮（layers.py::analyze_volume）
    "R1": 15, "R2": 15,                     # RSI 超買／超賣（layers.py::analyze_rsi）
}

# (score floor, status code, status label) — first band whose floor the score clears.
POSITION_BANDS = (
    (20.0, "LOW", "低檔"),
    (-20.0, "MID", "中檔"),
    (float("-inf"), "HIGH", "高檔"),
)

# 跟 decision.py 的 verdict 交叉出的雙軸標籤——只覆蓋「趨勢有表態」（偏多/偏空）的情況；
# 中性趨勢維持原本「中性」文字，不疊加位置警示，避免中性又要講位置、語意過載。
DUAL_LABELS = {
    ("bullish", "LOW"): ("strong_position", "🟢 積極布局"),
    ("bullish", "MID"): ("normal_position", "🟡 分批布局"),
    ("bullish", "HIGH"): ("overheated", "🟠 高檔偏多（持有觀望）"),
    ("bearish", "HIGH"): ("weak_position", "🔴 減碼"),
    ("bearish", "MID"): ("weak_position", "🔴 減碼"),
    ("bearish", "LOW"): ("oversold_watch", "⚪ 等待止穩"),
}


def _position_status(score: float) -> tuple[str, str]:
    for floor, code, label in POSITION_BANDS:
        if score >= floor:
            return code, label
    return "HIGH", "高檔"  # unreachable: last band floor is -inf


def _trend_side(verdict: str) -> str:
    if verdict in ("strong_buy", "buy"):
        return "bullish"
    if verdict in ("strong_sell", "sell"):
        return "bearish"
    return "neutral"


def analyze(decision_result: dict) -> dict:
    reasons: list[dict] = []
    raw_total = 0.0

    for s in decision_result["signals"]:
        weight = POSITION_SIGNAL_WEIGHTS.get(s["code"])
        if weight is None:
            continue
        signed = weight if s["side"] == "buy" else -weight
        raw_total += signed
        reasons.append({**s, "position_contribution": signed})

    score = round(max(-100.0, min(100.0, raw_total)), 1)
    status_code, status_label = _position_status(score)
    reasons.sort(key=lambda r: -abs(r["position_contribution"]))

    trend_side = _trend_side(decision_result["verdict"])
    dual_code, dual_label = DUAL_LABELS.get(
        (trend_side, status_code), (None, decision_result["verdict_label"])
    )

    return {
        "position_score": score,
        "position_status": status_code,
        "position_status_label": status_label,
        "position_reasons": reasons,
        "dual_verdict_code": dual_code,
        "dual_verdict_label": dual_label,
    }
