"""每日 8:30 自動晨報 (V4.0 Step 2) — 把 `overnight_sentiment.run()` 的結果每日存一份快照。

Doesn't recompute or alter the scoring logic at all — this module is purely the
persist/read-back layer on top of the already-validated `overnight_sentiment` service, so a
GitHub Actions cron (or a manual call, or the homepage's fallback button) can trigger generation
once and every subsequent page load just reads the saved row instead of re-running the ~10s live
pipeline.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MorningBriefing, StockWatchlist
from app.services import overnight_sentiment
from app.services.verification import taiwan_today


async def generate_and_save(db: AsyncSession, swing_entries: list[StockWatchlist]) -> MorningBriefing:
    result = await overnight_sentiment.run(swing_entries)
    briefing_date = taiwan_today()

    stmt = pg_insert(MorningBriefing).values(
        briefing_date=briefing_date,
        macro=result["macro"],
        stocks=result["stocks"],
        generated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["briefing_date"],
        set_={
            "macro": stmt.excluded.macro,
            "stocks": stmt.excluded.stocks,
            "generated_at": stmt.excluded.generated_at,
        },
    ).returning(MorningBriefing)

    row = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return row


async def get_latest(db: AsyncSession) -> MorningBriefing | None:
    result = await db.execute(select(MorningBriefing).order_by(MorningBriefing.briefing_date.desc()).limit(1))
    return result.scalars().first()
