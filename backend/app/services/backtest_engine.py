"""V3.6 回測統計引擎 — stub only（第一支柱：資料結構擴充）。

Real implementation (deferred, not built here): given today's fired-signal
"fingerprint" — the set of signal codes from granville/waves/layers/chips,
e.g. [D3, K1, V1] — scan a multi-year historical signal database for prior
occurrences of the same fingerprint across the universe, then compute the
20-trading-day-later up-probability / average return / win-rate grade from
those historical matches. That historical database doesn't exist yet, so
this always returns None for all three fields; callers/PDF/frontend already
wire up the fields now so nothing else needs to change once the real engine
lands.
"""


def compute_backtest_stats(symbol: str | None) -> dict:
    return {
        "backtest_20d_up_prob": None,
        "backtest_avg_return": None,
        "signal_win_rate_grade": None,
    }
