"""Layer 3-7 technical signals (KD / MACD / 均線乖離率 / RSI / 成交量).

Same style as `granville.py`: plain threshold/crossover rules over the
indicator series already computed by `indicators.compute_all`, returning
both the latest values (for display) and a `signals` list (for the
decision engine).
"""

import statistics

KD_OVERBOUGHT = 80.0
KD_OVERSOLD = 20.0

RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0

BIAS_EXTREME_FLOOR = {5: 3.0, 10: 4.0, 60: 8.0, 120: 12.0, 240: 18.0}
BIAS_EXTREME_MULT = 2.0
BIAS_SIGNAL_WINDOWS = (5, 10, 60, 120, 240)  # 20 excluded: already covered by Granville B4/S4

VOLUME_SURGE_MULT = 1.5
VOLUME_SHRINK_MULT = 0.5


def analyze_kd(ind: dict) -> dict:
    k, d = ind["kd"]["k"], ind["kd"]["d"]
    signals: list[dict] = []

    if len(k) >= 2 and None not in (k[-1], k[-2], d[-1], d[-2]):
        prev_k, prev_d, cur_k, cur_d = k[-2], d[-2], k[-1], d[-1]

        if prev_k < prev_d and cur_k > cur_d:
            low_zone = cur_k < KD_OVERSOLD + 10
            signals.append({
                "code": "K1" if low_zone else "K1-mid", "side": "buy",
                "label": "低檔黃金交叉" if low_zone else "KD黃金交叉",
                "tier": "weak", "confidence": 40,
                "reason": f"K({cur_k:.1f}) 向上穿越 D({cur_d:.1f})" + ("，且位於低檔" if low_zone else ""),
            })
        if prev_k > prev_d and cur_k < cur_d:
            high_zone = cur_k > KD_OVERBOUGHT - 10
            signals.append({
                "code": "K2" if high_zone else "K2-mid", "side": "sell",
                "label": "高檔死亡交叉" if high_zone else "KD死亡交叉",
                "tier": "weak", "confidence": 40,
                "reason": f"K({cur_k:.1f}) 向下穿越 D({cur_d:.1f})" + ("，且位於高檔" if high_zone else ""),
            })
        if cur_k >= KD_OVERBOUGHT and cur_d >= KD_OVERBOUGHT:
            signals.append({
                "code": "K3", "side": "sell", "label": "KD 超買",
                "tier": "medium", "confidence": 50,
                "reason": f"K/D 皆 ≥ {KD_OVERBOUGHT:.0f}，短線過熱",
            })
        if cur_k <= KD_OVERSOLD and cur_d <= KD_OVERSOLD:
            signals.append({
                "code": "K4", "side": "buy", "label": "KD 超賣",
                "tier": "medium", "confidence": 50,
                "reason": f"K/D 皆 ≤ {KD_OVERSOLD:.0f}，短線超跌",
            })

    return {"k": k[-1] if k else None, "d": d[-1] if d else None, "signals": signals}


def analyze_macd(ind: dict) -> dict:
    macd_line, signal_line, hist = ind["macd"]["macd"], ind["macd"]["signal"], ind["macd"]["histogram"]
    signals: list[dict] = []

    if len(macd_line) >= 2 and None not in (macd_line[-1], macd_line[-2], signal_line[-1], signal_line[-2]):
        prev_m, prev_s, cur_m, cur_s = macd_line[-2], signal_line[-2], macd_line[-1], signal_line[-1]

        if prev_m < prev_s and cur_m > cur_s:
            below_zero = cur_m < 0
            signals.append({
                "code": "D1", "side": "buy", "label": "MACD 黃金交叉",
                "tier": "medium", "confidence": 50,
                "reason": f"MACD({cur_m:.2f}) 向上穿越訊號線({cur_s:.2f})"
                + ("，位於零軸下方，反彈訊號較強" if below_zero else ""),
            })
        if prev_m > prev_s and cur_m < cur_s:
            above_zero = cur_m > 0
            signals.append({
                "code": "D2", "side": "sell", "label": "MACD 死亡交叉",
                "tier": "medium", "confidence": 50,
                "reason": f"MACD({cur_m:.2f}) 向下穿越訊號線({cur_s:.2f})"
                + ("，位於零軸上方，回落訊號較強" if above_zero else ""),
            })

        if prev_m <= 0 < cur_m:
            signals.append({
                "code": "D3", "side": "buy", "label": "MACD 站上零軸",
                "tier": "strong", "confidence": 70,
                "reason": "MACD 由負轉正，多方動能轉強",
            })
        if prev_m >= 0 > cur_m:
            signals.append({
                "code": "D4", "side": "sell", "label": "MACD 跌破零軸",
                "tier": "strong", "confidence": 70,
                "reason": "MACD 由正轉負，空方動能轉強",
            })

    return {
        "macd": macd_line[-1] if macd_line else None,
        "signal": signal_line[-1] if signal_line else None,
        "histogram": hist[-1] if hist else None,
        "signals": signals,
    }


def analyze_bias(ind: dict) -> dict:
    bias = ind["bias"]
    latest = {window: series[-1] if series else None for window, series in bias.items()}
    signals: list[dict] = []

    for window in BIAS_SIGNAL_WINDOWS:
        series = bias.get(str(window))
        if not series or series[-1] is None:
            continue
        valid = [v for v in series if v is not None]
        if len(valid) < 30:
            continue
        recent = valid[-60:]
        std = statistics.pstdev(recent) if len(recent) > 1 else 0.0
        threshold = max(BIAS_EXTREME_FLOOR.get(window, 5.0), std * BIAS_EXTREME_MULT)
        value = series[-1]

        if value >= threshold:
            signals.append({
                "code": f"BI{window}-high", "side": "sell", "label": f"{window}日乖離過大（正）",
                "tier": "weak", "confidence": 40,
                "reason": f"乖離率 {value:.2f}%，偏離{window}日均線過多，留意拉回",
            })
        if value <= -threshold:
            signals.append({
                "code": f"BI{window}-low", "side": "buy", "label": f"{window}日乖離過大（負）",
                "tier": "weak", "confidence": 40,
                "reason": f"乖離率 {value:.2f}%，偏離{window}日均線過多，留意反彈",
            })

    return {"latest": latest, "signals": signals}


def analyze_rsi(ind: dict) -> dict:
    rsi6, rsi14 = ind["rsi"]["6"], ind["rsi"]["14"]
    signals: list[dict] = []

    if rsi14 and rsi14[-1] is not None:
        value = rsi14[-1]
        if value >= RSI_OVERBOUGHT:
            signals.append({
                "code": "R1", "side": "sell", "label": "RSI 超買",
                "tier": "medium", "confidence": 50,
                "reason": f"RSI14 {value:.1f}，短線過熱",
            })
        if value <= RSI_OVERSOLD:
            signals.append({
                "code": "R2", "side": "buy", "label": "RSI 超賣",
                "tier": "medium", "confidence": 50,
                "reason": f"RSI14 {value:.1f}，短線超跌",
            })

    if len(rsi6) >= 2 and len(rsi14) >= 2 and None not in (rsi6[-1], rsi6[-2], rsi14[-1], rsi14[-2]):
        prev6, prev14, cur6, cur14 = rsi6[-2], rsi14[-2], rsi6[-1], rsi14[-1]
        if prev6 < prev14 and cur6 > cur14:
            signals.append({
                "code": "R3", "side": "buy", "label": "RSI 短多交叉",
                "tier": "weak", "confidence": 40,
                "reason": "RSI6 向上穿越 RSI14，短線動能轉強",
            })
        if prev6 > prev14 and cur6 < cur14:
            signals.append({
                "code": "R4", "side": "sell", "label": "RSI 短空交叉",
                "tier": "weak", "confidence": 40,
                "reason": "RSI6 向下穿越 RSI14，短線動能轉弱",
            })

    return {"rsi6": rsi6[-1] if rsi6 else None, "rsi14": rsi14[-1] if rsi14 else None, "signals": signals}


def analyze_volume(ind: dict) -> dict:
    volume, close, vol_ma20 = ind["volume"], ind["close"], ind["volume_ma"]["20"]
    signals: list[dict] = []

    if (
        len(volume) >= 2
        and vol_ma20
        and vol_ma20[-1]
        and close[-1] is not None
        and close[-2] is not None
    ):
        cur_vol, avg_vol = volume[-1], vol_ma20[-1]
        price_up = close[-1] > close[-2]
        surge = cur_vol >= avg_vol * VOLUME_SURGE_MULT
        shrink = cur_vol <= avg_vol * VOLUME_SHRINK_MULT

        if surge and price_up:
            signals.append({
                "code": "V1", "side": "buy", "label": "價漲量增",
                "tier": "medium", "confidence": 50,
                "reason": "成交量放大且股價上漲，買盤動能增強",
            })
        if surge and not price_up:
            signals.append({
                "code": "V2", "side": "sell", "label": "價跌量增",
                "tier": "medium", "confidence": 50,
                "reason": "成交量放大但股價下跌，賣壓沉重",
            })
        if shrink and price_up:
            signals.append({
                "code": "V3", "side": "sell", "label": "價漲量縮",
                "tier": "weak", "confidence": 40,
                "reason": "股價上漲但量能萎縮，追價意願不足，留意過熱",
            })
        if shrink and not price_up:
            signals.append({
                "code": "V4", "side": "buy", "label": "價跌量縮",
                "tier": "weak", "confidence": 40,
                "reason": "股價下跌但量能萎縮，賣壓趨緩，留意止跌",
            })

    return {
        "volume": volume[-1] if volume else None,
        "volume_ma20": vol_ma20[-1] if vol_ma20 else None,
        "signals": signals,
    }


def analyze_layers(ind: dict) -> dict:
    """Layers 3-7 combined, for both display and the decision engine."""
    kd = analyze_kd(ind)
    macd = analyze_macd(ind)
    bias = analyze_bias(ind)
    rsi = analyze_rsi(ind)
    volume = analyze_volume(ind)
    signals = sorted(
        kd["signals"] + macd["signals"] + bias["signals"] + rsi["signals"] + volume["signals"],
        key=lambda s: -s["confidence"],
    )
    return {"kd": kd, "macd": macd, "bias": bias, "rsi": rsi, "volume": volume, "signals": signals}
