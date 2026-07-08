import pandas as pd

DIRECTION_LOOKBACK = 5
DIRECTION_THRESHOLD = 0.001  # 0.1% change over the lookback window counts as trending, not flat

# Significance thresholds below are scaled to each stock's own recent bias20
# volatility rather than fixed percentages — a stock like TSMC can swing its
# bias20 by 1-2 points a day as pure noise, while a low-volatility ETF might
# never move that much even during a real signal. Floors keep the thresholds
# sane for near-flat stocks.
BIAS_EXTREME_FLOOR = 3.0  # percent
BIAS_EXTREME_MULT = 2.0  # x rolling std of bias20 level
DIP_BIAS_FLOOR = 0.5  # percent
DIP_BIAS_MULT = 1.0  # x rolling std of day-over-day bias20 change
BIAS_SHIFT_FLOOR = 0.3  # percent
BIAS_SHIFT_MULT = 0.75  # x rolling std of day-over-day bias20 change


def _direction(series: pd.Series, lookback: int = DIRECTION_LOOKBACK) -> str | None:
    if len(series) <= lookback:
        return None
    prev, cur = series.iloc[-1 - lookback], series.iloc[-1]
    if pd.isna(prev) or pd.isna(cur) or prev == 0:
        return None
    change = (cur - prev) / abs(prev)
    if change > DIRECTION_THRESHOLD:
        return "up"
    if change < -DIRECTION_THRESHOLD:
        return "down"
    return "flat"


def _direction_at(series: pd.Series, end_offset: int, lookback: int = DIRECTION_LOOKBACK) -> str | None:
    """Direction as of `end_offset` bars before the last bar (0 = latest)."""
    trimmed = series.iloc[: len(series) - end_offset] if end_offset else series
    return _direction(trimmed, lookback)


def _ma_alignment(ma20: float, ma60: float, ma120: float) -> str:
    if pd.isna(ma20) or pd.isna(ma60) or pd.isna(ma120):
        return "unknown"
    if ma20 > ma60 > ma120:
        return "bullish"
    if ma20 < ma60 < ma120:
        return "bearish"
    return "mixed"


def analyze(df: pd.DataFrame, ind: dict) -> dict:
    """Granville's 8 rules against MA20, plus MA20/60/120 direction and alignment context."""
    close, volume = df["Close"], df["Volume"]
    ma20 = pd.Series(ind["ma"]["20"], index=df.index, dtype="float64")
    ma60 = pd.Series(ind["ma"]["60"], index=df.index, dtype="float64")
    ma120 = pd.Series(ind["ma"]["120"], index=df.index, dtype="float64")
    bias20 = pd.Series(ind["bias"]["20"], index=df.index, dtype="float64")
    vol_ma20 = pd.Series(ind["volume_ma"]["20"], index=df.index, dtype="float64")

    dir20, dir60, dir120 = _direction(ma20), _direction(ma60), _direction(ma120)
    alignment = _ma_alignment(ma20.iloc[-1], ma60.iloc[-1], ma120.iloc[-1])

    bias_level_std = bias20.rolling(60).std().iloc[-1]
    bias_diff_std = bias20.diff().rolling(20).std().iloc[-1]
    extreme_threshold = max(BIAS_EXTREME_FLOOR, (bias_level_std or 0) * BIAS_EXTREME_MULT)
    dip_threshold = max(DIP_BIAS_FLOOR, (bias_diff_std or 0) * DIP_BIAS_MULT)
    shift_threshold = max(BIAS_SHIFT_FLOOR, (bias_diff_std or 0) * BIAS_SHIFT_MULT)

    signals: list[dict] = []

    prior_dir20 = _direction_at(ma20, end_offset=DIRECTION_LOOKBACK)

    if len(close) >= 2 and not pd.isna(ma20.iloc[-2]) and not pd.isna(ma20.iloc[-1]):
        prev_close, cur_close = close.iloc[-2], close.iloc[-1]
        prev_ma, cur_ma = ma20.iloc[-2], ma20.iloc[-1]
        crossed_up = prev_close < prev_ma and cur_close > cur_ma
        crossed_down = prev_close > prev_ma and cur_close < cur_ma

        # B1/S1 mark a genuine trend reversal, not just any dip-and-cross while
        # the trend is already established — require the MA direction itself to
        # have just turned, not merely be currently up/down.
        turned_up = dir20 == "up" and prior_dir20 != "up"
        turned_down = dir20 == "down" and prior_dir20 != "down"

        if crossed_up and turned_up:
            signals.append({
                "code": "B1", "side": "buy", "label": "回升買進",
                "confidence": 70,
                "reason": "均線剛轉為上升，股價由下往上穿越MA20",
            })
        if crossed_down and turned_down:
            signals.append({
                "code": "S1", "side": "sell", "label": "跌破賣出",
                "confidence": 70,
                "reason": "均線剛轉為下降，股價由上往下跌破MA20",
            })

    window = 5
    if len(close) > window and not vol_ma20.isna().iloc[-1] and not bias20.iloc[-window:].isna().any():
        recent_bias = bias20.iloc[-window:-1]
        vol_ok = not pd.isna(volume.iloc[-1]) and volume.iloc[-1] >= vol_ma20.iloc[-1]

        if dir20 == "up":
            dipped_below = recent_bias.min() <= -dip_threshold
            reclaimed = close.iloc[-1] > ma20.iloc[-1]
            if dipped_below and reclaimed:
                if vol_ok:
                    signals.append({
                        "code": "B2", "side": "buy", "label": "假跌破支撐買點",
                        "confidence": 65, "reason": "均線仍上升，股價短暫跌破後帶量收回MA20之上",
                    })
                else:
                    signals.append({
                        "code": "B2-weak", "side": "buy", "label": "疑似假B2（量能不足）",
                        "confidence": 35, "reason": "股價雖收回MA20之上，但成交量未達20日均量，訊號可信度較低",
                    })

        if dir20 == "down":
            popped_above = recent_bias.max() >= dip_threshold
            fell_back = close.iloc[-1] < ma20.iloc[-1]
            if popped_above and fell_back:
                if vol_ok:
                    signals.append({
                        "code": "S2", "side": "sell", "label": "假突破反壓賣點",
                        "confidence": 65, "reason": "均線仍下降，股價短暫突破後帶量跌回MA20之下",
                    })
                else:
                    signals.append({
                        "code": "S2-weak", "side": "sell", "label": "疑似假S2（量能不足）",
                        "confidence": 35, "reason": "股價雖跌回MA20之下，但成交量未達20日均量，訊號可信度較低",
                    })

    if len(bias20) > 3 and not bias20.iloc[-4:].isna().any():
        b = bias20.iloc[-4:]
        narrowed = b.iloc[-3] - b.iloc[-2]
        widened = b.iloc[-1] - b.iloc[-2]
        if dir20 == "up":
            never_crossed = (close.iloc[-4:] > ma20.iloc[-4:]).all()
            narrowed_then_widened = narrowed >= shift_threshold and widened >= shift_threshold and b.iloc[-1] > 0
            if never_crossed and narrowed_then_widened:
                signals.append({
                    "code": "B3", "side": "buy", "label": "回檔不破支撐買點",
                    "confidence": 60, "reason": "股價未跌破MA20，乖離收斂後再度擴大",
                })
        if dir20 == "down":
            never_crossed = (close.iloc[-4:] < ma20.iloc[-4:]).all()
            narrowed_then_widened = narrowed <= -shift_threshold and widened <= -shift_threshold and b.iloc[-1] < 0
            if never_crossed and narrowed_then_widened:
                signals.append({
                    "code": "S3", "side": "sell", "label": "反彈不過壓力賣點",
                    "confidence": 60, "reason": "股價未突破MA20，乖離收斂後再度擴大",
                })

    if len(close) >= 2 and not pd.isna(bias20.iloc[-1]):
        if bias20.iloc[-1] <= -extreme_threshold and close.iloc[-1] > close.iloc[-2]:
            signals.append({
                "code": "B4", "side": "buy", "label": "超跌反彈買點",
                "confidence": 55, "reason": f"乖離率 {bias20.iloc[-1]:.2f}% 超跌，出現反彈跡象",
            })
        if bias20.iloc[-1] >= extreme_threshold and close.iloc[-1] < close.iloc[-2]:
            signals.append({
                "code": "S4", "side": "sell", "label": "超漲回落賣點",
                "confidence": 55, "reason": f"乖離率 {bias20.iloc[-1]:.2f}% 過熱，出現回落跡象",
            })

    return {
        "ma20_direction": dir20,
        "ma60_direction": dir60,
        "ma120_direction": dir120,
        "ma_alignment": alignment,
        "signals": signals,
        "thresholds": {
            "extreme_bias": round(extreme_threshold, 3),
            "dip_bias": round(dip_threshold, 3),
            "shift_bias": round(shift_threshold, 3),
        },
    }
