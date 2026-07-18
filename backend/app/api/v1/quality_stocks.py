from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import QualityStockCandidate

router = APIRouter(prefix="/quality-stocks", tags=["quality-stocks"])


def _serialize(row: QualityStockCandidate) -> dict:
    return {
        "rank": row.rank,
        "symbol": row.symbol,
        "name": row.name,
        "market": row.market,
        "price": row.price,
        "fcf_return_latest_pct": row.fcf_return_latest_pct,
        "fcf_return_3y_avg_pct": row.fcf_return_3y_avg_pct,
        "pb_ratio": row.pb_ratio,
        "pb_rank": row.pb_rank,
        "pe_ratio": row.pe_ratio,
        "pe_rank": row.pe_rank,
        "dividend_yield_pct": row.dividend_yield_pct,
        "yield_rank": row.yield_rank,
        "combined_score": row.combined_score,
        "screened_at": row.screened_at.isoformat(),
    }


@router.get("")
async def list_quality_stocks(db: AsyncSession = Depends(get_db)) -> dict:
    """讀取最新一次財報狗績優股清單批次篩選結果（不觸發即時掃描——全市場批次需數小時，
    只能由 `backend/scripts/screen_quality_stocks.py` 手動或排程觸發，這裡只讀取快照）。
    """
    result = await db.execute(select(QualityStockCandidate).order_by(QualityStockCandidate.rank))
    rows = list(result.scalars().all())
    return {
        "screened_at": rows[0].screened_at.isoformat() if rows else None,
        "stocks": [_serialize(row) for row in rows],
    }
