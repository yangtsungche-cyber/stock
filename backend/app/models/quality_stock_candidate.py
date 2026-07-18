"""財報狗績優股清單 (Quality Stock Screener) 的快照表。

Same whole-table-replace-on-each-run shape as `FundamentalCandidate` — see
that model's docstring. This is a separate table (not a variant of
`fundamental_candidates`) because it's a distinct methodology/ranking, not
the same 8-criterion checklist screen.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QualityStockCandidate(Base):
    __tablename__ = "quality_stock_candidates"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    fcf_return_latest_pct: Mapped[float] = mapped_column(Float, nullable=False)
    fcf_return_3y_avg_pct: Mapped[float] = mapped_column(Float, nullable=False)
    pb_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    pb_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    pe_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    pe_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    dividend_yield_pct: Mapped[float] = mapped_column(Float, nullable=False)
    yield_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    combined_score: Mapped[int] = mapped_column(Integer, nullable=False)
    screened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
