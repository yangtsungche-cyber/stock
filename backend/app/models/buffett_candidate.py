"""巴菲特選股清單 (Buffett Stock Screener) 的快照表。

Same whole-table-replace-on-each-run shape as `QualityStockCandidate` — see that model's
docstring. Unlike the quality-stock screen (which ranks survivors by PB/PE/殖利率), the Buffett
screen's 9 conditions are pure AND-gated pass/fail with no inherent ranking — `rank` here just
reflects a presentation-only sort (5-year-average ROE descending, see `buffett_screening.py`),
not part of the original methodology.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BuffettCandidate(Base):
    __tablename__ = "buffett_candidates"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_ratio_latest_pct: Mapped[float] = mapped_column(Float, nullable=False)
    debt_ratio_3y_avg_pct: Mapped[float] = mapped_column(Float, nullable=False)
    debt_ratio_5y_avg_pct: Mapped[float] = mapped_column(Float, nullable=False)
    roe_latest_pct: Mapped[float] = mapped_column(Float, nullable=False)
    roe_3y_avg_pct: Mapped[float] = mapped_column(Float, nullable=False)
    roe_5y_avg_pct: Mapped[float] = mapped_column(Float, nullable=False)
    fcf_per_share_latest: Mapped[float] = mapped_column(Float, nullable=False)
    fcf_per_share_3y_avg: Mapped[float] = mapped_column(Float, nullable=False)
    fcf_per_share_5y_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_lots: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    screened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
