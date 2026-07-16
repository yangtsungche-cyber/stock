"""分析驗證中心批次回填 (V3.2 sub-system #6)。

執行方式（於 backend/ 目錄下）：
    python scripts/backfill_analysis_returns.py

對 analysis_history 中所有尚未滿 20 個交易日的紀錄逐筆檢查，滿 20 個交易日的
就補上 price_t20/return_20d_pct；未滿的維持原樣，之後再跑一次即可。適合排入
每日/每週排程（例如 GitHub Actions），也可以手動執行——與 screen_fundamentals.py
一樣，這個專案目前偏好先手動觸發，之後有需要再上排程。
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.services import verification  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_analysis_returns")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        updated = await verification.backfill_matured(session)

    logger.info("回填完成，本次更新 %d 筆紀錄", updated)


if __name__ == "__main__":
    asyncio.run(main())
