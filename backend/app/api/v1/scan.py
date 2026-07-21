from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import FundamentalCandidate, StockWatchlist
from app.services import scan, verification

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
async def run_market_scan(
    symbols: str | None = Query(None, description="逗號分隔股票代號，測試/單股重跑用，略過自選股池＋候選池合併"),
) -> dict:
    """首頁「開始 AI 掃描」：合併自選股池（啟用中）+ 基本面候選池，跑完整分析流程，回傳 AI 市場總表。

    每次掃描同時把結果寫入 analysis_history（分析驗證中心，sub-system #6）
    的快照，供未來回填 20 天後報酬率、計算勝率等統計使用。
    """
    symbols_override = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None

    watchlist_entries: list[StockWatchlist] = []
    candidates: list[FundamentalCandidate] = []
    if symbols_override is None:
        # No `Depends(get_db)` here on purpose — that session would sit open (and idle) across
        # the multi-minute `run_scan` call below, and Neon (serverless Postgres) closes
        # connections that sit idle that long, so it'd go stale before FastAPI tears the
        # dependency down at request end (raised as an unhandled rollback-on-closed-connection
        # error, harmless to the response but noisy). Same reasoning as
        # `portfolio.build_dashboard`'s DB-reads-before-the-long-scan fix and this endpoint's own
        # already-fresh `write_db` session below — every DB touch here is short-lived and closed
        # immediately, never held across `run_scan`.
        async with AsyncSessionLocal() as read_db:
            watchlist_result = await read_db.execute(select(StockWatchlist).where(StockWatchlist.enabled.is_(True)))
            candidates_result = await read_db.execute(select(FundamentalCandidate))
            watchlist_entries = list(watchlist_result.scalars().all())
            candidates = list(candidates_result.scalars().all())

    results = await scan.run_scan(watchlist_entries, candidates, symbols_override=symbols_override)

    async with AsyncSessionLocal() as write_db:
        await verification.record_history(write_db, results, verification.taiwan_today())

    return {"count": len(results), "results": results}
