from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import StockWatchlist
from app.services import overnight_sentiment

router = APIRouter(prefix="/overnight-sentiment", tags=["overnight-sentiment"])


@router.get("")
async def get_overnight_sentiment(db: AsyncSession = Depends(get_db)) -> dict:
    """第九層：全球市場情緒分析 (V4.0 MVP) — 隔夜總經 + 個股籌碼，僅涵蓋自選股池中「波段」分類的股票。

    核心/長期持股（category=="核心"）刻意不出現在這裡——定期定額累積策略不該被短線隔夜雜訊干擾。
    """
    result = await db.execute(
        select(StockWatchlist).where(StockWatchlist.enabled.is_(True), StockWatchlist.category == "波段")
    )
    return await overnight_sentiment.run(list(result.scalars().all()))
