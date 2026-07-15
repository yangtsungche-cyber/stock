"""全市場基本面候選池批次作業 (V3.2 sub-system #2)。

執行方式（於 backend/ 目錄下）：
    python scripts/screen_fundamentals.py                      # 全市場，約 12-15 小時
    python scripts/screen_fundamentals.py --universe-limit 15  # 小規模測試，幾分鐘內跑完
    python scripts/screen_fundamentals.py --dry-run            # 不寫入 Neon，只印出結果

設計要點（與使用者確認過，見 memory 'stock-v32-fundamental-data-research'）：
FinMind 免費版全市場批次拉取會被擋（需付費），但單股查詢（`data_id`）不受限——所以這支
script 花數小時逐檔查詢 FinMind，全程不連線 Neon；只有在最後把排名結果寫入資料庫時才
建立連線，寫完立刻關閉。這樣 15 小時的爬蟲只佔用 Neon 免費額度（100 CU-hr/月）幾秒鐘。
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import FundamentalCandidate  # noqa: E402
from app.services import screening  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("screen_fundamentals")


def _progress(done: int, total: int, symbol: str) -> None:
    if done % 10 == 0 or done == total:
        logger.info("%d/%d（目前：%s）", done, total, symbol)


async def _write_to_db(candidates: list[dict]) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(FundamentalCandidate))
        for rank, c in enumerate(candidates, start=1):
            session.add(FundamentalCandidate(
                symbol=c["symbol"],
                rank=rank,
                name=c["name"],
                market=c["market"],
                industry_category=c["industry_category"],
                rating=c["rating"],
                rating_label=c["rating_label"],
                summary=c["summary"],
                checklist=c["checklist"],
                daily_volume_lots=c["daily_volume_lots"],
            ))
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="全市場基本面候選池批次篩選")
    parser.add_argument("--limit", type=int, default=20, help="輸出候選股數量（預設 20）")
    parser.add_argument("--universe-limit", type=int, default=None, help="限制掃描檔數（測試用）")
    parser.add_argument("--symbols", type=str, default=None, help="指定股票代號清單（逗號分隔，測試用，略過全市場清單）")
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫，只印出結果")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else None

    start = time.monotonic()
    logger.info("開始全市場基本面篩選（universe_limit=%s, symbols=%s）", args.universe_limit, symbols)
    candidates = screening.screen_all(
        limit=args.limit, universe_limit=args.universe_limit, symbols=symbols, on_progress=_progress
    )
    elapsed = time.monotonic() - start
    logger.info("篩選完成，耗時 %.1f 分鐘，候選股 %d 檔", elapsed / 60, len(candidates))

    for rank, c in enumerate(candidates, start=1):
        print(f"{rank:>2}. {c['symbol']} {c['name']}（{c['market']}）★{c['rating']:.1f} — {c['summary']}")

    if args.dry_run:
        logger.info("--dry-run：略過資料庫寫入")
        return

    asyncio.run(_write_to_db(candidates))
    logger.info("已寫入 Neon（%d 筆，資料表 fundamental_candidates）", len(candidates))


if __name__ == "__main__":
    main()
