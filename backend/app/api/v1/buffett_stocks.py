from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import BuffettCandidate

router = APIRouter(prefix="/buffett-stocks", tags=["buffett-stocks"])


def _serialize(row: BuffettCandidate) -> dict:
    return {
        "rank": row.rank,
        "symbol": row.symbol,
        "name": row.name,
        "market": row.market,
        "price": row.price,
        "debt_ratio_latest_pct": row.debt_ratio_latest_pct,
        "debt_ratio_3y_avg_pct": row.debt_ratio_3y_avg_pct,
        "debt_ratio_5y_avg_pct": row.debt_ratio_5y_avg_pct,
        "roe_latest_pct": row.roe_latest_pct,
        "roe_3y_avg_pct": row.roe_3y_avg_pct,
        "roe_5y_avg_pct": row.roe_5y_avg_pct,
        "fcf_per_share_latest": row.fcf_per_share_latest,
        "fcf_per_share_3y_avg": row.fcf_per_share_3y_avg,
        "fcf_per_share_5y_avg": row.fcf_per_share_5y_avg,
        "volume_lots": row.volume_lots,
        "screened_at": row.screened_at.isoformat(),
    }


@router.get("")
async def list_buffett_stocks(db: AsyncSession = Depends(get_db)) -> dict:
    """讀取最新一次巴菲特選股清單批次篩選結果（不觸發即時掃描——全市場批次需數小時，
    只能由 `backend/scripts/screen_buffett_stocks.py` 手動或排程觸發，這裡只讀取快照）。
    """
    result = await db.execute(select(BuffettCandidate).order_by(BuffettCandidate.rank))
    rows = list(result.scalars().all())
    return {
        "screened_at": rows[0].screened_at.isoformat() if rows else None,
        "stocks": [_serialize(row) for row in rows],
    }
