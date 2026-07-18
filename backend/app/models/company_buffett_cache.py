"""每股自由現金流／ROE／負債比率的逐年快取 — 巴菲特選股批次用。

Deliberately a separate, independent cache from `CompanyFcfCache` even though both ultimately
read overlapping FinMind datasets (`TaiwanStockBalanceSheet`/`TaiwanStockCashFlowsStatement`) —
this one also needs `TaiwanStockFinancialStatements` (for ROE's net-income figure), and widening
the already-populated, already-incident-tested `company_fcf_cache` table right after stabilizing
it was judged not worth the risk for the modest efficiency gain. Same accumulating-cache shape
(never wholesale-replaced, only per-symbol upserted) and same freshness-check convention
(`fetched_at` vs. the most recently passed 台股法定財報截止日) as `CompanyFcfCache` — see
`buffett_screening.py`.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyBuffettCache(Base):
    __tablename__ = "company_buffett_cache"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)
    debt_ratio_by_year: Mapped[dict] = mapped_column(JSON, nullable=False)
    roe_by_year: Mapped[dict] = mapped_column(JSON, nullable=False)
    fcf_per_share_by_year: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
