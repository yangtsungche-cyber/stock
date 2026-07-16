from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import FundamentalCandidate, StockWatchlist
from app.services import scan

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
async def run_market_scan(db: AsyncSession = Depends(get_db)) -> dict:
    """首頁「開始 AI 掃描」：合併自選股池（啟用中）+ 基本面候選池，跑完整分析流程，回傳 AI 市場總表。"""
    watchlist_result = await db.execute(select(StockWatchlist).where(StockWatchlist.enabled.is_(True)))
    candidates_result = await db.execute(select(FundamentalCandidate))
    watchlist_entries = list(watchlist_result.scalars().all())
    candidates = list(candidates_result.scalars().all())

    results = await scan.run_scan(watchlist_entries, candidates)
    return {"count": len(results), "results": results}
