"""自選股池 (V3.2 sub-system #1) — 使用者自行管理的關注股票清單。

Plain CRUD table, no derived analysis of its own. This is the input list
sub-system #5's future "開始 AI 掃描" merges with the fundamental candidate
pool (`FundamentalCandidate`) before running the full per-stock pipeline.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockWatchlist(Base):
    __tablename__ = "stock_watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    stock_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # 核心 / 波段 / 觀察
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
