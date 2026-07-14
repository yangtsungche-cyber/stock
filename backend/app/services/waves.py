"""Layer 2: 波浪理論 (Elliott Wave), pragmatic version.

Elliott Wave has no universally-agreed hard rules, so this module takes a
percentage/ATR-based ZigZag over the price series to find swing pivots, then
checks the trailing 6 pivots (5 legs) against the three hard Elliott rules
for an impulse, or the trailing 4 pivots (3 legs) for a simple A-B-C
correction. Same output shape as `granville.py`/`layers.py`: latest state
for display plus a `signals` list for the decision engine.
"""

import pandas as pd

ATR_WINDOW = 14
THRESHOLD_FLOOR = 0.05  # 5% minimum swing to register as a pivot
THRESHOLD_ATR_MULT = 3.5  # x average ATR%, converts a 1-day range into a swing-scale threshold

FIB_RETRACE_MIN = 0.236
FIB_RETRACE_MAX = 0.786


def _atr_threshold(high: pd.Series, low: pd.Series, close: pd.Series) -> float:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr = true_range.rolling(ATR_WINDOW).mean()
    atr_pct = (atr / close).dropna()
    avg_atr_pct = float(atr_pct.mean()) if len(atr_pct) else 0.0
    return max(THRESHOLD_FLOOR, avg_atr_pct * THRESHOLD_ATR_MULT)


def _zigzag_pivots(dates: list[str], high: pd.Series, low: pd.Series, threshold: float) -> list[dict]:
    """Standard percentage ZigZag over high/low. Returns confirmed pivots plus
    a trailing provisional pivot for the still-forming swing."""
    n = len(high)
    if n == 0:
        return []

    h, l = high.to_numpy(), low.to_numpy()
    pivots: list[tuple[int, float, str]] = []

    direction = 0  # 0 = undecided, 1 = tracking a high, -1 = tracking a low
    cand_high, cand_high_idx = h[0], 0
    cand_low, cand_low_idx = l[0], 0
    extreme_price, extreme_idx = 0.0, 0

    for i in range(1, n):
        if direction == 0:
            if h[i] > cand_high:
                cand_high, cand_high_idx = h[i], i
            if l[i] < cand_low:
                cand_low, cand_low_idx = l[i], i
            if cand_high_idx < i and l[i] <= cand_high * (1 - threshold):
                pivots.append((cand_high_idx, cand_high, "H"))
                direction = -1
                extreme_price, extreme_idx = l[i], i
            elif cand_low_idx < i and h[i] >= cand_low * (1 + threshold):
                pivots.append((cand_low_idx, cand_low, "L"))
                direction = 1
                extreme_price, extreme_idx = h[i], i
        elif direction == 1:
            if h[i] > extreme_price:
                extreme_price, extreme_idx = h[i], i
            elif l[i] <= extreme_price * (1 - threshold):
                pivots.append((extreme_idx, extreme_price, "H"))
                direction = -1
                extreme_price, extreme_idx = l[i], i
        elif direction == -1:
            if l[i] < extreme_price:
                extreme_price, extreme_idx = l[i], i
            elif h[i] >= extreme_price * (1 + threshold):
                pivots.append((extreme_idx, extreme_price, "L"))
                direction = 1
                extreme_price, extreme_idx = h[i], i

    if direction == 1:
        pivots.append((extreme_idx, extreme_price, "H"))
    elif direction == -1:
        pivots.append((extreme_idx, extreme_price, "L"))

    return [{"date": dates[idx], "price": round(float(price), 2), "type": kind} for idx, price, kind in pivots]


def _check_impulse(prices: list[float], up: bool) -> tuple[bool, list[str]]:
    """3 hard Elliott rules for a 5-leg impulse (6 points P0..P5)."""
    p0, p1, p2, p3, p4, p5 = prices
    w1, w3, w5 = abs(p1 - p0), abs(p3 - p2), abs(p5 - p4)
    violations: list[str] = []

    if up:
        if p2 <= p0:
            violations.append("第2波跌破第1波起點（違反規則）")
        if p4 <= p1:
            violations.append("第4波與第1波價格區間重疊（違反規則）")
    else:
        if p2 >= p0:
            violations.append("第2波漲過第1波起點（違反規則）")
        if p4 >= p1:
            violations.append("第4波與第1波價格區間重疊（違反規則）")

    if w3 < w1 and w3 < w5:
        violations.append("第3波是三波中最短（違反規則）")

    return (len(violations) == 0, violations)


def _fib_ratio(a: float, b: float) -> float | None:
    return round(abs(b) / abs(a), 3) if a else None


def analyze(df: pd.DataFrame) -> dict:
    dates = [idx.strftime("%Y-%m-%d") for idx in df.index]
    high, low, close = df["High"], df["Low"], df["Close"]

    threshold = _atr_threshold(high, low, close)
    pivots = _zigzag_pivots(dates, high, low, threshold)

    signals: list[dict] = []
    pattern = "insufficient_data"
    wave_labels: list[dict] = []
    current_position = "資料不足，無法辨識波浪結構（需要更多明顯的價格擺動）"

    if len(pivots) >= 6:
        last6 = pivots[-6:]
        prices = [p["price"] for p in last6]
        up = last6[0]["type"] == "L"  # starts at a low => impulse up
        expected = ["L", "H", "L", "H", "L", "H"] if up else ["H", "L", "H", "L", "H", "L"]
        shape_ok = [p["type"] for p in last6] == expected

        if shape_ok:
            valid, violations = _check_impulse(prices, up)
            labels = ["0", "1", "2", "3", "4", "5"]
            wave_labels = [{**pt, "label": lbl} for pt, lbl in zip(last6, labels)]

            if valid:
                pattern = "impulse_up" if up else "impulse_down"
                side = "sell" if up else "buy"
                current_position = (
                    f"疑似{'上升' if up else '下降'}五波已於 {last6[-1]['date']} "
                    f"完成第5波（{last6[-1]['price']}），留意反轉"
                )
                signals.append({
                    "code": "W5" if up else "W5-down",
                    "side": side,
                    "label": "五波完成疑似反轉",
                    "confidence": 50,
                    "reason": current_position,
                })
                w1 = abs(prices[1] - prices[0])
                w3 = abs(prices[3] - prices[2])
                w5 = abs(prices[5] - prices[4])
                if w3 >= w1 and w3 >= w5:
                    signals.append({
                        "code": "W3", "side": "buy" if up else "sell",
                        "label": "第3波為延伸波",
                        "confidence": 45,
                        "reason": "第3波幅度為三推動波中最大，符合主升/主跌段特徵",
                    })
            else:
                pattern = "impulse_up_invalid" if up else "impulse_down_invalid"
                current_position = "偵測到五段擺動，但不符合艾略特波浪硬性規則：" + "；".join(violations)
    elif len(pivots) >= 4:
        last4 = pivots[-4:]
        prices = [p["price"] for p in last4]
        up = last4[0]["type"] == "H"  # starts at a high => corrective down-then-up (a-b-c off a top)... generic ABC
        expected_down = ["H", "L", "H", "L"]
        expected_up = ["L", "H", "L", "H"]
        shape = [p["type"] for p in last4]

        if shape in (expected_down, expected_up):
            labels = ["起點", "A", "B", "C"]
            wave_labels = [{**pt, "label": lbl} for pt, lbl in zip(last4, labels)]
            leg_a = abs(prices[1] - prices[0])
            leg_b = abs(prices[2] - prices[1])
            leg_c = abs(prices[3] - prices[2])
            b_retrace = _fib_ratio(leg_a, leg_b)
            c_a_ratio = _fib_ratio(leg_a, leg_c)
            corrective_down = shape == expected_down  # A/C legs point down => this was a downward correction

            if b_retrace is not None and FIB_RETRACE_MIN <= b_retrace <= FIB_RETRACE_MAX:
                pattern = "corrective_down" if corrective_down else "corrective_up"
                side = "buy" if corrective_down else "sell"
                current_position = (
                    f"疑似 A-B-C 三波修正於 {last4[-1]['date']} 完成 C 波"
                    f"（B 波拉回 {b_retrace:.1%}，C/A 比 {c_a_ratio}），留意結束後反轉"
                )
                signals.append({
                    "code": "WC", "side": side,
                    "label": "ABC修正波疑似完成",
                    "confidence": 40,
                    "reason": current_position,
                })
            else:
                pattern = "corrective_down_unclear" if corrective_down else "corrective_up_unclear"
                current_position = "偵測到三段擺動，但 B 波拉回幅度不在常見費波南希區間，型態不明確"

    return {
        "threshold_pct": round(threshold, 4),
        "pivots": pivots[-12:],
        "pattern": pattern,
        "wave_labels": wave_labels,
        "current_position": current_position,
        "signals": signals,
    }
