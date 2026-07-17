import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.morning_briefing import router as morning_briefing_router
from app.api.v1.overnight_sentiment import router as overnight_sentiment_router
from app.api.v1.scan import router as scan_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.verification import router as verification_router
from app.api.v1.watchlist import router as watchlist_router
from app.core.config import get_settings
from app.core.database import Base, engine

logger = logging.getLogger(__name__)

# 給 Neon 免費方案從 autosuspend 喚醒的緩衝時間 —— 見 README_V4_DEPLOY.md 第 2 節，
# 這是一次離峰時段（Neon compute 剛好處於暫停狀態）啟動崩潰事故的根因分析。
DB_STARTUP_RETRY_ATTEMPTS = 3
DB_STARTUP_RETRY_DELAY_SECONDS = 3

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(morning_briefing_router, prefix="/api/v1")
app.include_router(overnight_sentiment_router, prefix="/api/v1")
app.include_router(scan_router, prefix="/api/v1")
app.include_router(stocks_router, prefix="/api/v1")
app.include_router(verification_router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")


@app.on_event("startup")
async def create_tables() -> None:
    # No Alembic migrations yet — fine for this project's current scale, see
    # memory 'stock-project-step-progress' Step 10. Revisit once schema
    # changes need to preserve existing data instead of just adding tables.
    #
    # Retries + swallows the final failure on purpose: an uncaught exception here aborts
    # FastAPI's whole ASGI lifespan startup, so uvicorn never starts accepting requests at
    # all — Cloud Run then marks the revision unhealthy and every caller gets a 503 that
    # looks like an API bug but is actually "the container never finished starting." A
    # transient DB connect failure (e.g. Neon's free-tier compute waking from autosuspend)
    # should degrade to "DB-dependent endpoints error until the DB is reachable," not take
    # down the entire service — same philosophy as this app's existing has_data:false
    # graceful-degradation pattern (chips.py/fundamentals.py/overnight_sentiment.py), just
    # applied to the startup lifespan.
    for attempt in range(1, DB_STARTUP_RETRY_ATTEMPTS + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            logger.exception(
                "create_tables 第 %d/%d 次嘗試失敗，資料庫可能尚在啟動或喚醒中",
                attempt, DB_STARTUP_RETRY_ATTEMPTS,
            )
            if attempt < DB_STARTUP_RETRY_ATTEMPTS:
                await asyncio.sleep(DB_STARTUP_RETRY_DELAY_SECONDS)

    logger.error("create_tables 最終仍失敗，服務照常啟動，但資料庫相關端點在資料庫恢復前都會回傳錯誤")
