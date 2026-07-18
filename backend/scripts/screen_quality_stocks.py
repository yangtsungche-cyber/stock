"""財報狗績優股清單批次作業。

執行方式（於 backend/ 目錄下）：
    python scripts/screen_quality_stocks.py                      # 全市場，實際耗時視流動性門檻篩掉多少檔而定
    python scripts/screen_quality_stocks.py --universe-limit 15  # 小規模測試，幾分鐘內跑完
    python scripts/screen_quality_stocks.py --dry-run            # 不寫入 Neon，只印出結果
    python scripts/screen_quality_stocks.py --max-hours 7.5      # 時間預算：到時間就停，把目前掃到的結果寫入
    python scripts/screen_quality_stocks.py --refresh-cache      # 忽略現有快取，強制重抓每一檔的財報數據

同 `screen_fundamentals.py` 的離線爬蟲、最後才短暫連線 Neon 一次性寫入的設計，
只是換一套排序邏輯（見 `app.services.quality_screening`）與獨立的輸出資料表
`quality_stock_candidates`，不影響既有的 `fundamental_candidates`。

財報快取（`company_fcf_cache`）：`TaiwanStockBalanceSheet`/`TaiwanStockCashFlowsStatement`
只在公司申報季報/年報時才變動（法定截止日 3/31、5/15、8/14、11/14），每次重跑若已有
「涵蓋最近一次已過截止日」的快取，就直接沿用、完全不打 FinMind——這是唯一會讓每次重跑
變快、變省額度的地方，跟本檔案開頭之外的其餘設計（全市場離線爬蟲、批次一次性寫入）無關。
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import CompanyFcfCache, QualityStockCandidate  # noqa: E402
from app.services import quality_screening  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("screen_quality_stocks")


def _progress(done: int, total: int, symbol: str) -> None:
    if done % 10 == 0 or done == total:
        logger.info("%d/%d（目前：%s）", done, total, symbol)


async def _load_cache() -> dict[str, dict]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CompanyFcfCache))
        rows = result.scalars().all()

    return {
        row.symbol: {
            "name": row.name,
            "market": row.market,
            "fcf_return_by_year": row.fcf_return_by_year,
            "fetched_at": row.fetched_at,
        }
        for row in rows
    }


async def _write_to_db(candidates: list[dict], fcf_cache: dict[str, dict]) -> None:
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
                price=c["price"],
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

        for symbol, entry in fcf_cache.items():
            stmt = pg_insert(CompanyFcfCache).values(
                symbol=symbol,
                name=entry["name"],
                market=entry["market"],
                fcf_return_by_year=entry["fcf_return_by_year"],
                fetched_at=entry["fetched_at"],
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "fcf_return_by_year": stmt.excluded.fcf_return_by_year,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
            await session.execute(stmt)

        await session.commit()


async def _run(args: argparse.Namespace) -> None:
    # One event loop for the whole script (load -> sync scan -> write) — splitting
    # this across separate `asyncio.run()` calls left a stale asyncpg connection
    # bound to an already-closed loop by the time the write step ran (confirmed by
    # hitting "RuntimeError: Event loop is closed" during testing).
    symbols = args.symbols.split(",") if args.symbols else None
    max_seconds = args.max_hours * 3600 if args.max_hours is not None else None

    fcf_cache = {} if args.refresh_cache else await _load_cache()
    logger.info("財報快取現有 %d 檔%s", len(fcf_cache), "（本次強制忽略，全部重抓）" if args.refresh_cache else "")

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
        fcf_cache=fcf_cache,
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
        logger.info("--dry-run：略過資料庫寫入（含財報快取）")
        return

    await _write_to_db(candidates, fcf_cache)
    logger.info(
        "已寫入 Neon（%d 筆績優股於 quality_stock_candidates，%d 筆財報快取於 company_fcf_cache）",
        len(candidates), len(fcf_cache),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="財報狗績優股清單批次篩選")
    parser.add_argument("--limit", type=int, default=80, help="輸出候選股數量（預設 80）")
    parser.add_argument("--universe-limit", type=int, default=None, help="限制掃描檔數（測試用）")
    parser.add_argument("--symbols", type=str, default=None, help="指定股票代號清單（逗號分隔，測試用，略過全市場清單）")
    parser.add_argument("--max-hours", type=float, default=None, help="時間預算（小時）：到時間就停止掃描，把目前為止的結果排名並寫入")
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫（含財報快取），只印出結果")
    parser.add_argument("--refresh-cache", action="store_true", help="忽略現有財報快取，強制對每一檔重新呼叫 FinMind")
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
