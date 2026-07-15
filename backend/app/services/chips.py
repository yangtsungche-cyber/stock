"""Chip-side (籌碼面) analysis: margin/short balances and 三大法人 buy/sell trends.

Mirrors the style of `granville.analyze` — plain threshold rules over the raw
TWSE history, returning both derived metrics (for table display) and a
`signals` list (for the decision engine in a later step).
"""

MARGIN_SURGE_PCT = 5.0  # day-over-day balance change considered "大幅" (percent)
MARGIN_STREAK_MIN = 3  # consecutive days of same-direction change to flag a trend
SHORT_MARGIN_RATIO_HIGH = 30.0  # percent; conventional watch level for short-squeeze risk

INSTITUTIONAL_STREAK_MIN = 3
ROLLING_WINDOWS = (5, 20)
ROLLING_FIELDS = ("foreign_net", "trust_net", "dealer_net", "total_net")


def _pct_change(curr: float, prev: float) -> float | None:
    if not prev:
        return None
    return round((curr - prev) / abs(prev) * 100, 2)


def _streak(rows: list[dict], field: str) -> dict:
    """Length/direction of the most recent run of same-signed values in `field`."""
    direction, days = None, 0
    for row in reversed(rows):
        value = row.get(field, 0)
        current = "up" if value > 0 else ("down" if value < 0 else "flat")
        if direction is None:
            direction, days = current, 1
        elif current == direction and current != "flat":
            days += 1
        else:
            break
    return {"direction": direction, "days": days}


def analyze_margin(history: list[dict]) -> dict:
    rows = []
    for row in history:
        margin_today = row.get("margin_today_balance", 0)
        margin_prev = row.get("margin_prev_balance", 0)
        short_today = row.get("short_today_balance", 0)
        short_prev = row.get("short_prev_balance", 0)
        rows.append({
            **row,
            "margin_change": margin_today - margin_prev,
            "margin_change_pct": _pct_change(margin_today, margin_prev),
            "short_change": short_today - short_prev,
            "short_change_pct": _pct_change(short_today, short_prev),
            "short_margin_ratio": round(short_today / margin_today * 100, 2) if margin_today else None,
        })

    streak = _streak(rows, "margin_change")
    signals: list[dict] = []

    if rows:
        latest = rows[-1]
        change_pct = latest["margin_change_pct"]
        if change_pct is not None and abs(change_pct) >= MARGIN_SURGE_PCT:
            surging = change_pct > 0
            signals.append({
                "code": "M1" if surging else "M1-r",
                "side": "sell" if surging else "buy",
                "label": "融資餘額大幅增加" if surging else "融資餘額大幅減少",
                "confidence": 55,
                "reason": (
                    f"融資餘額單日變動 {change_pct:+.2f}%，追高風險上升"
                    if surging
                    else f"融資餘額單日變動 {change_pct:+.2f}%，籌碼降溫"
                ),
            })

        ratio = latest["short_margin_ratio"]
        if ratio is not None and ratio >= SHORT_MARGIN_RATIO_HIGH:
            signals.append({
                "code": "M2", "side": "buy", "label": "券資比偏高，留意軋空",
                "confidence": 50,
                "reason": f"券資比 {ratio:.2f}%，融券回補若加速可能推升股價",
            })

        if streak["days"] >= MARGIN_STREAK_MIN and streak["direction"] in ("up", "down"):
            rising = streak["direction"] == "up"
            signals.append({
                "code": "M3" if rising else "M3-r",
                "side": "sell" if rising else "buy",
                "label": f"融資餘額連續 {streak['days']} 日增加" if rising else f"融資餘額連續 {streak['days']} 日減少",
                "confidence": 45,
                "reason": "融資餘額持續增加，散戶追價意願提高" if rising else "融資餘額持續減少，籌碼趨於清淡",
            })

    return {"history": rows, "streak": streak, "signals": signals, "has_data": bool(rows)}


def analyze_institutional(history: list[dict]) -> dict:
    if not history:
        return {
            "streak": {"direction": None, "days": 0},
            "rolling": {},
            "signals": [],
            "has_data": False,
        }

    streak = _streak(history, "total_net")

    def rolling_sum(field: str, n: int) -> int:
        return sum(r.get(field, 0) for r in history[-n:])

    rolling = {
        f"{n}d": {field: rolling_sum(field, n) for field in ROLLING_FIELDS}
        for n in ROLLING_WINDOWS
    }

    signals: list[dict] = []
    latest = history[-1]

    if streak["days"] >= INSTITUTIONAL_STREAK_MIN and streak["direction"] in ("up", "down"):
        buying = streak["direction"] == "up"
        signals.append({
            "code": "I1" if buying else "I2",
            "side": "buy" if buying else "sell",
            "label": f"三大法人連續 {streak['days']} 日買超" if buying else f"三大法人連續 {streak['days']} 日賣超",
            "confidence": 60,
            "reason": "三大法人買超力道延續，籌碼面轉強" if buying else "三大法人賣超力道延續，籌碼面轉弱",
        })

    foreign_net, trust_net = latest.get("foreign_net", 0), latest.get("trust_net", 0)
    if foreign_net > 0 and trust_net > 0:
        signals.append({
            "code": "I3", "side": "buy", "label": "外資投信同步買超",
            "confidence": 55, "reason": "外資與投信同日買超，籌碼集中度高",
        })
    elif foreign_net < 0 and trust_net < 0:
        signals.append({
            "code": "I4", "side": "sell", "label": "外資投信同步賣超",
            "confidence": 55, "reason": "外資與投信同日賣超，籌碼面轉弱",
        })

    if len(history) >= 2:
        prev_foreign = history[-2].get("foreign_net", 0)
        if prev_foreign <= 0 and foreign_net > 0:
            signals.append({
                "code": "I5", "side": "buy", "label": "外資由賣轉買",
                "confidence": 45, "reason": "外資賣超轉為買超，留意風向轉變",
            })
        elif prev_foreign >= 0 and foreign_net < 0:
            signals.append({
                "code": "I6", "side": "sell", "label": "外資由買轉賣",
                "confidence": 45, "reason": "外資買超轉為賣超，留意風向轉變",
            })

    return {"streak": streak, "rolling": rolling, "signals": signals, "has_data": True}


def analyze(margin_history: list[dict], institutional_history: list[dict]) -> dict:
    """Combined 第八層 (chip-side) signal set for the decision engine."""
    margin = analyze_margin(margin_history)
    institutional = analyze_institutional(institutional_history)
    signals = sorted(margin["signals"] + institutional["signals"], key=lambda s: -s["confidence"])
    return {"margin": margin, "institutional": institutional, "signals": signals}
