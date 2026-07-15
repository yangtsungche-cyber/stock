"""基本面候選池 (V3.2 sub-system #2) 的快照表。

Each screening run *replaces* the table's contents wholesale (see
`backend/scripts/screen_fundamentals.py`) — this holds the current top-N
candidates, not a history of past runs. Historical tracking of AI scores
over time belongs to sub-system #6's separate `analysis_history` table
(not built yet), not here.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FundamentalCandidate(Base):
    __tablename__ = "fundamental_candidates"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    industry_category: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=False)
    rating_label: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    checklist: Mapped[list] = mapped_column(JSON, nullable=False)
    daily_volume_lots: Mapped[float | None] = mapped_column(Float, nullable=True)
    screened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
