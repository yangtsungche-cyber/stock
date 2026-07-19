"""使用者實際持股庫存快照表。

Whole-table-replace snapshot **per `owner`**, same shape as
`FundamentalCandidate`/`QualityStockCandidate` (just scoped) — each import via
`POST /api/v1/portfolio/import` replaces that one owner's rows, since a brokerage
"未實現損益" screenshot is itself always a complete current-holdings snapshot for one account,
not an incremental buy/sell delta. Re-importing after any trade is the update mechanism; there is
no separate buy/sell ledger.

`owner` (e.g. 我/太太/女兒) + `symbol` together are the primary key — different family members
can hold the same stock, so `symbol` alone can no longer be unique.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserPortfolio(Base):
    __tablename__ = "user_portfolio"

    owner: Mapped[str] = mapped_column(String, primary_key=True)
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
