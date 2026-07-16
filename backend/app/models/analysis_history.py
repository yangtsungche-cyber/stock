"""分析驗證中心 (V3.2 sub-system #6) 的分析歷史紀錄表。

Every "AI 掃描" run (sub-system #5) writes one row per successfully-analyzed
stock, snapshotting that day's technical/fundamental verdict plus that day's
close price (`price_t0`). `price_t20`/`return_20d_pct` start out NULL and are
filled in later — once 20 *trading* days have actually elapsed — by
`verification.backfill_matured`. Until then a row is simply "not yet mature"
(there is no way to know a 20-day return before 20 trading days have passed),
not a data-quality problem. `(stock_code, analysis_date)` is unique: re-
running a scan the same day updates that day's snapshot rather than piling up
duplicate same-day rows.

`layer_directions` stores each layer's fired direction ("buy"/"sell"/
"neutral"/"no_data") at analysis time — needed to compute per-indicator
false-positive rates once the eventual return is known, without having to
re-derive it from `decision.py`'s `layer_breakdown` after the fact.
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"
    __table_args__ = (UniqueConstraint("stock_code", "analysis_date", name="uq_analysis_history_symbol_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String, nullable=False)
    stock_name: Mapped[str | None] = mapped_column(String, nullable=True)
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)

    technical_score: Mapped[float] = mapped_column(Float, nullable=False)
    technical_verdict: Mapped[str] = mapped_column(String, nullable=False)
    fundamental_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    combined_label: Mapped[str] = mapped_column(String, nullable=False)
    confidence_pct: Mapped[float] = mapped_column(Float, nullable=False)
    layer_directions: Mapped[dict] = mapped_column(JSON, nullable=False)

    price_t0: Mapped[float] = mapped_column(Float, nullable=False)
    price_t20: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_20d_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
