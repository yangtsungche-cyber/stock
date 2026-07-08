import pandas as pd

MA_WINDOWS = [5, 10, 20, 60, 120, 240]


def compute_ma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window).mean()


def compute_bias(close: pd.Series, ma: pd.Series) -> pd.Series:
    return (close - ma) / ma * 100


def compute_kd(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 9,
) -> tuple[pd.Series, pd.Series]:
    """Taiwan-style KD (RSV smoothed 2/3 prev + 1/3 new), seeded at 50."""
    lowest_low = low.rolling(window=n).min()
    highest_high = high.rolling(window=n).max()
    denom = (highest_high - lowest_low).replace(0, pd.NA)
    rsv = (close - lowest_low) / denom * 100

    k_values: list[float | None] = []
    d_values: list[float | None] = []
    prev_k, prev_d = 50.0, 50.0

    for value in rsv:
        if pd.isna(value):
            k_values.append(None)
            d_values.append(None)
            continue
        cur_k = prev_k * 2 / 3 + float(value) * 1 / 3
        cur_d = prev_d * 2 / 3 + cur_k * 1 / 3
        k_values.append(cur_k)
        d_values.append(cur_d)
        prev_k, prev_d = cur_k, cur_d

    return (
        pd.Series(k_values, index=rsv.index, dtype="float64"),
        pd.Series(d_values, index=rsv.index, dtype="float64"),
    )


def compute_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def compute_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume).cumsum()


def _series_to_list(series: pd.Series, decimals: int = 2) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), decimals) for v in series]


def compute_all(df: pd.DataFrame) -> dict:
    """Compute the full indicator set for the eight-layer model from an OHLCV DataFrame."""
    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

    ma = {w: compute_ma(close, w) for w in MA_WINDOWS}
    bias = {w: compute_bias(close, ma[w]) for w in MA_WINDOWS}
    k, d = compute_kd(high, low, close)
    macd_line, signal_line, histogram = compute_macd(close)
    rsi6 = compute_rsi(close, 6)
    rsi14 = compute_rsi(close, 14)
    obv = compute_obv(close, volume)
    vol_ma5 = volume.rolling(window=5).mean()
    vol_ma20 = volume.rolling(window=20).mean()

    dates = [idx.strftime("%Y-%m-%d") for idx in df.index]

    return {
        "dates": dates,
        "close": _series_to_list(close),
        "volume": [int(v) for v in volume],
        "ma": {str(w): _series_to_list(ma[w]) for w in MA_WINDOWS},
        "bias": {str(w): _series_to_list(bias[w], 3) for w in MA_WINDOWS},
        "kd": {"k": _series_to_list(k), "d": _series_to_list(d)},
        "macd": {
            "macd": _series_to_list(macd_line, 3),
            "signal": _series_to_list(signal_line, 3),
            "histogram": _series_to_list(histogram, 3),
        },
        "rsi": {"6": _series_to_list(rsi6), "14": _series_to_list(rsi14)},
        "obv": [int(v) for v in obv],
        "volume_ma": {"5": _series_to_list(vol_ma5, 0), "20": _series_to_list(vol_ma20, 0)},
    }
