"""市值歷史走勢圖上的日期註記——使用者標記「這天市值大幅變化的原因」（例如大筆支出、
增資匯入等), 純粹是使用者自己寫的備忘, 不影響任何計算。刻意不分成員（我/太太/女兒）,
因為這類事件通常是全家層級的財務事件, 跟哪一條線無關, 保持一個共用時間軸即可, 不需要
再多一個維度。
"""

from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioAnnotation(Base):
    __tablename__ = "portfolio_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    note: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
