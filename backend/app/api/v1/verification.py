from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import AnalysisHistory
from app.services import verification

router = APIRouter(prefix="/verification", tags=["verification"])


class HistoryOut(BaseModel):
    id: int
    stock_code: str
    analysis_date: date
    technical_score: float
    technical_verdict: str
    fundamental_rating: float | None
    combined_label: str
    confidence_pct: float
    price_t0: float
    price_t20: float | None
    return_20d_pct: float | None
    backfilled_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("/history", response_model=list[HistoryOut])
async def list_history(
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[AnalysisHistory]:
    """分析驗證中心：原始歷史紀錄（依分析日期新到舊）。"""
    result = await db.execute(
        select(AnalysisHistory).order_by(AnalysisHistory.analysis_date.desc(), AnalysisHistory.stock_code).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """分析驗證中心：勝率／平均報酬／避開下跌比例／各指標假陽性率，僅計入已滿 20 個交易日的紀錄。"""
    result = await db.execute(select(AnalysisHistory))
    rows = list(result.scalars().all())
    return verification.compute_stats(rows)


@router.post("/backfill")
async def run_backfill(db: AsyncSession = Depends(get_db)) -> dict:
    """手動觸發：對所有尚未滿 20 個交易日的紀錄嘗試回填 T+20 收盤價與報酬率。"""
    updated = await verification.backfill_matured(db)
    return {"updated": updated}
