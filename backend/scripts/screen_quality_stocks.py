"""財報狗績優股清單批次作業。

執行方式（於 backend/ 目錄下）：
    python scripts/screen_quality_stocks.py                      # 全市場，實際耗時視流動性門檻篩掉多少檔而定
    python scripts/screen_quality_stocks.py --universe-limit 15  # 小規模測試，幾分鐘內跑完
    python scripts/screen_quality_stocks.py --dry-run            # 不寫入 Neon，只印出結果
    python scripts/screen_quality_stocks.py --max-hours 7.5      # 時間預算：到時間就停，把目前掃到的結果寫入

同 `screen_fundamentals.py` 的離線爬蟲、最後才短暫連線 Neon 一次性寫入的設計，
只是換一套排序邏輯（見 `app.services.quality_screening`）與獨立的輸出資料表
`quality_stock_candidates`，不影響既有的 `fundamental_candidates`。
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
from app.models import QualityStockCandidate  # noqa: E402
from app.services import quality_screening  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("screen_quality_stocks")


def _progress(done: int, total: int, symbol: str) -> None:
    if done % 10 == 0 or done == total:
        logger.info("%d/%d（目前：%s）", done, total, symbol)


async def _write_to_db(candidates: list[dict]) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(QualityStockCandidate))
        for rank, c in enumerate(candidates, start=1):
            session.add(QualityStockCandidate(
                symbol=c["symbol"],
                rank=rank,
                name=c["name"],
                market=c["market"],
                fcf_return_latest_pct=c["fcf_return_latest_pct"],
                fcf_return_3y_avg_pct=c["fcf_return_3y_avg_pct"],
                pb_ratio=c["pb_ratio"],
                pb_rank=c["pb_rank"],
                pe_ratio=c["pe_ratio"],
                pe_rank=c["pe_rank"],
                dividend_yield_pct=c["dividend_yield_pct"],
                yield_rank=c["yield_rank"],
                combined_score=c["combined_score"],
            ))
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="財報狗績優股清單批次篩選")
    parser.add_argument("--limit", type=int, default=80, help="輸出候選股數量（預設 80）")
    parser.add_argument("--universe-limit", type=int, default=None, help="限制掃描檔數（測試用）")
    parser.add_argument("--symbols", type=str, default=None, help="指定股票代號清單（逗號分隔，測試用，略過全市場清單）")
    parser.add_argument("--max-hours", type=float, default=None, help="時間預算（小時）：到時間就停止掃描，把目前為止的結果排名並寫入")
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫，只印出結果")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else None
    max_seconds = args.max_hours * 3600 if args.max_hours is not None else None

    start = time.monotonic()
    logger.info(
        "開始財報狗績優股清單篩選（universe_limit=%s, symbols=%s, max_hours=%s）",
        args.universe_limit, symbols, args.max_hours,
    )
    candidates = quality_screening.screen_all(
        limit=args.limit,
        universe_limit=args.universe_limit,
        symbols=symbols,
        max_seconds=max_seconds,
        on_progress=_progress,
    )
    elapsed = time.monotonic() - start
    logger.info("篩選完成，耗時 %.1f 分鐘，績優股 %d 檔", elapsed / 60, len(candidates))

    for rank, c in enumerate(candidates, start=1):
        print(
            f"{rank:>2}. {c['symbol']} {c['name']}（{c['market']}）"
            f"3年FCF報酬率均值={c['fcf_return_3y_avg_pct']:.2f}% "
            f"PB={c['pb_ratio']:.2f}(#{c['pb_rank']}) PE={c['pe_ratio']:.2f}(#{c['pe_rank']}) "
            f"殖利率={c['dividend_yield_pct']:.2f}%(#{c['yield_rank']}) 綜合分數={c['combined_score']}"
        )

    if args.dry_run:
        logger.info("--dry-run：略過資料庫寫入")
        return

    asyncio.run(_write_to_db(candidates))
    logger.info("已寫入 Neon（%d 筆，資料表 quality_stock_candidates）", len(candidates))


if __name__ == "__main__":
    main()
