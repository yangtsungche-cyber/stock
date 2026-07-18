"""每股年度自由現金流報酬率快取 — 財報狗績優股清單批次用，避免每次重跑都重打 FinMind。

Unlike `QualityStockCandidate`/`FundamentalCandidate` (whole-table-replace snapshots), this
table *accumulates* across runs — each run upserts only the symbols it actually re-fetched
from FinMind, and leaves every other symbol's existing cached entry untouched. That's the
whole point: `TaiwanStockBalanceSheet`/`TaiwanStockCashFlowsStatement` only change when a
company files its quarterly report (法定截止日 3/31 年報、5/15 Q1、8/14 Q2、11/14 Q3), so
re-fetching a symbol whose cache already reflects the most recently-passed deadline is pure
waste — see `quality_screening.py`'s `_is_cache_fresh` for the exact check.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyFcfCache(Base):
    __tablename__ = "company_fcf_cache"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    fcf_return_by_year: Mapped[dict] = mapped_column(JSON, nullable=False)  # {"2023": 12.34, ...} — string year keys, JSON requirement
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
