"""一次性種子腳本：把使用者既有的自選股寫入 stock_watchlist（V3.2 sub-system #1）。

執行方式（於 backend/ 目錄下）：
    python scripts/seed_watchlist.py

Idempotent：已存在的 stock_code 會被略過，不會重複插入或覆蓋使用者後續的手動編輯。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import StockWatchlist  # noqa: E402

SEED = [
    ("2330", "台積電", "核心"),
    ("2317", "鴻海", "核心"),
    ("0050", "元大台灣50", "核心"),
    ("00713", "元大台灣高息低波", "核心"),
    ("1519", "華城", "波段"),
    ("3551", "世禾", "波段"),
    ("3402", "漢科", "波段"),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existing = set((await session.execute(select(StockWatchlist.stock_code))).scalars().all())
        added = 0
        for stock_code, stock_name, category in SEED:
            if stock_code in existing:
                continue
            session.add(StockWatchlist(stock_code=stock_code, stock_name=stock_name, category=category))
            added += 1
        await session.commit()
        print(f"新增 {added} 筆，略過 {len(SEED) - added} 筆（已存在）")


if __name__ == "__main__":
    asyncio.run(main())
