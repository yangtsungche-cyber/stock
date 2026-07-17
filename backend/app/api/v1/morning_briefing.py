from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import MorningBriefing, StockWatchlist
from app.services import morning_briefing

router = APIRouter(prefix="/morning-briefing", tags=["morning-briefing"])


def _serialize(row: MorningBriefing) -> dict:
    return {
        "briefing_date": row.briefing_date.isoformat(),
        "generated_at": row.generated_at.isoformat(),
        "macro": row.macro,
        "stocks": row.stocks,
    }


@router.post("/generate")
async def generate_morning_briefing(db: AsyncSession = Depends(get_db)) -> dict:
    """產生（或覆蓋）今日晨報快照，僅涵蓋自選股池中「波段」分類的股票——與 `/overnight-sentiment` 同一批。

    設計給每日 8:30 的排程（GitHub Actions）呼叫，也可手動觸發用於測試或即時刷新。
    """
    result = await db.execute(
        select(StockWatchlist).where(StockWatchlist.enabled.is_(True), StockWatchlist.category == "波段")
    )
    row = await morning_briefing.generate_and_save(db, list(result.scalars().all()))
    return _serialize(row)


@router.get("/latest")
async def get_latest_morning_briefing(db: AsyncSession = Depends(get_db)) -> dict:
    row = await morning_briefing.get_latest(db)
    if row is None:
        raise HTTPException(status_code=404, detail="尚無晨報紀錄，請先產生一次")
    return _serialize(row)
