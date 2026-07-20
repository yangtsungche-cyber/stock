from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.models import FundamentalCandidate, StockWatchlist
from app.services import scan, verification

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
async def run_market_scan(
    symbols: str | None = Query(None, description="逗號分隔股票代號，測試/單股重跑用，略過自選股池＋候選池合併"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """首頁「開始 AI 掃描」：合併自選股池（啟用中）+ 基本面候選池，跑完整分析流程，回傳 AI 市場總表。

    每次掃描同時把結果寫入 analysis_history（分析驗證中心，sub-system #6）
    的快照，供未來回填 20 天後報酬率、計算勝率等統計使用。
    """
    symbols_override = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None

    watchlist_entries: list[StockWatchlist] = []
    candidates: list[FundamentalCandidate] = []
    if symbols_override is None:
        watchlist_result = await db.execute(select(StockWatchlist).where(StockWatchlist.enabled.is_(True)))
        candidates_result = await db.execute(select(FundamentalCandidate))
        watchlist_entries = list(watchlist_result.scalars().all())
        candidates = list(candidates_result.scalars().all())

    results = await scan.run_scan(watchlist_entries, candidates, symbols_override=symbols_override)

    # `db` was opened before `run_scan`, which takes minutes for a full watchlist+candidate-pool
    # run — Neon (serverless Postgres) can close a connection that sits idle that long, so reusing
    # `db` here fails with "connection is closed" (same class of bug as `portfolio.build_dashboard`'s
    # DB-reads-before-the-long-scan fix; here we still need to *write* after the scan, so the fix is
    # a fresh session instead of avoiding the post-scan DB touch entirely).
    async with AsyncSessionLocal() as write_db:
        await verification.record_history(write_db, results, verification.taiwan_today())

    return {"count": len(results), "results": results}
