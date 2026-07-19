"""每日各成員（我/太太/女兒...）持股市值快照, 用來畫市值歷史走勢圖。

累積型資料表, 不是 whole-table-replace（每天新增一批 (date, owner) 列, 不覆蓋既有歷史）。
由 `POST /api/v1/portfolio/snapshot` 寫入, 該端點由每日排程（`.github/workflows/
portfolio-snapshot.yml`）呼叫——市值本身是用 `screening._load_daily_quotes` 的當日收盤價
快速算出（同 `portfolio.build_summary` 的算法), 不需要跑分鐘等級的技術面/基本面全掃描。
"""

from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioValueSnapshot(Base):
    __tablename__ = "portfolio_value_snapshots"

    date: Mapped[date_type] = mapped_column(Date, primary_key=True)
    owner: Mapped[str] = mapped_column(String, primary_key=True)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
