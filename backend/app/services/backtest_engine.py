"""V3.6 回測統計引擎（第一支柱：資料結構擴充 + 第二支柱：訊號特徵標籤化）。

Pillar 2 (this module, `build_fingerprint`): today's fired-signal "fingerprint"
— the sorted, deduped set of signal codes from granville/waves/layers/chips,
e.g. [D3, K1, V1] (each code already uniquely implies a side by construction,
see `decision.py`'s per-layer signal definitions) — is now actually built and
persisted every `/scan` run (`scan.py` → `verification.record_history` →
`analysis_history.signal_codes`), so a real historical backlog accumulates for
pillar 3 to search later, the same "let data accumulate before building the
consumer" precedent as the win-rate stats in `verification.py`.

Pillar 3 (still not built): scan that multi-year historical signal database
for prior occurrences of the *current* fingerprint across the universe, then
compute the 20-trading-day-later up-probability / average return / win-rate
grade from those historical matches. `compute_backtest_stats` already accepts
the live fingerprint as an argument (pre-wired, unused for now) so pillar 3 is
a pure algorithm swap-in later — no further plumbing/signature changes needed
in callers.
"""


def build_fingerprint(signals: list[dict]) -> list[str]:
    """今天觸發的所有訊號 code，去重＋排序成穩定的特徵向量（例如 ["D3", "K1", "V1"]）。"""
    return sorted({s["code"] for s in signals})


def compute_backtest_stats(symbol: str | None, fingerprint: list[str]) -> dict:
    return {
        "backtest_20d_up_prob": None,
        "backtest_avg_return": None,
        "signal_win_rate_grade": None,
    }
