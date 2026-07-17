"""每日 8:30 自動晨報 (V4.0 Step 2) — 第九層 overnight sentiment 的每日快照。

One row per calendar day (`briefing_date` unique), upserted whenever
`morning_briefing.generate_and_save` runs — regenerating the same day overwrites that day's
snapshot rather than piling up duplicates, same convention as `analysis_history`. `macro`/`stocks`
store exactly `overnight_sentiment.run()`'s own return shape verbatim, so the frontend can render
a saved briefing identically to a live one.
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MorningBriefing(Base):
    __tablename__ = "morning_briefing"
    __table_args__ = (UniqueConstraint("briefing_date", name="uq_morning_briefing_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False)
    macro: Mapped[dict] = mapped_column(JSON, nullable=False)
    stocks: Mapped[list] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
