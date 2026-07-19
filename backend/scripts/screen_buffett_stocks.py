"""巴菲特選股清單批次作業。

執行方式（於 backend/ 目錄下）：
    python scripts/screen_buffett_stocks.py                      # 全市場，實際耗時視流動性門檻篩掉多少檔而定
    python scripts/screen_buffett_stocks.py --universe-limit 15  # 小規模測試，幾分鐘內跑完
    python scripts/screen_buffett_stocks.py --dry-run            # 不寫入 Neon，只印出結果
    python scripts/screen_buffett_stocks.py --max-hours 7.5      # 時間預算：到時間就停，把目前掃到的結果寫入
    python scripts/screen_buffett_stocks.py --refresh-cache      # 忽略現有快取，強制重抓每一檔的財報數據

同 `screen_quality_stocks.py` 的離線爬蟲、最後才短暫連線 Neon 一次性寫入的設計，
只是換一套篩選邏輯（見 `app.services.buffett_screening`）與獨立的輸出資料表
`buffett_candidates` / 財報快取表 `company_buffett_cache`，不影響既有的
`quality_stock_candidates` / `company_fcf_cache`。
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import BuffettCandidate, CompanyBuffettCache  # noqa: E402
from app.services import buffett_screening  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("screen_buffett_stocks")


def _progress(done: int, total: int, symbol: str) -> None:
    if done % 10 == 0 or done == total:
        logger.info("%d/%d（目前：%s）", done, total, symbol)


async def _load_cache() -> dict[str, dict]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(CompanyBuffettCache))
        rows = result.scalars().all()

    return {
        row.symbol: {
            "name": row.name,
            "market": row.market,
            "debt_ratio_by_year": row.debt_ratio_by_year,
            "roe_by_year": row.roe_by_year,
            "fcf_per_share_by_year": row.fcf_per_share_by_year,
            "fetched_at": row.fetched_at,
        }
        for row in rows
    }


async def _write_to_db(candidates: list[dict], metrics_cache: dict[str, dict]) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(BuffettCandidate))
        for rank, c in enumerate(candidates, start=1):
            session.add(BuffettCandidate(
                symbol=c["symbol"],
                rank=rank,
                name=c["name"],
                market=c["market"],
                price=c["price"],
                debt_ratio_latest_pct=c["debt_ratio_latest_pct"],
                debt_ratio_3y_avg_pct=c["debt_ratio_3y_avg_pct"],
                debt_ratio_5y_avg_pct=c["debt_ratio_5y_avg_pct"],
                roe_latest_pct=c["roe_latest_pct"],
                roe_3y_avg_pct=c["roe_3y_avg_pct"],
                roe_5y_avg_pct=c["roe_5y_avg_pct"],
                fcf_per_share_latest=c["fcf_per_share_latest"],
                fcf_per_share_3y_avg=c["fcf_per_share_3y_avg"],
                fcf_per_share_5y_avg=c["fcf_per_share_5y_avg"],
                volume_lots=c.get("volume_lots"),
                dividend_yield_pct=c.get("dividend_yield_pct"),
            ))

        for symbol, entry in metrics_cache.items():
            stmt = pg_insert(CompanyBuffettCache).values(
                symbol=symbol,
                name=entry["name"],
                market=entry["market"],
                debt_ratio_by_year=entry["debt_ratio_by_year"],
                roe_by_year=entry["roe_by_year"],
                fcf_per_share_by_year=entry["fcf_per_share_by_year"],
                fetched_at=entry["fetched_at"],
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": stmt.excluded.name,
                    "market": stmt.excluded.market,
                    "debt_ratio_by_year": stmt.excluded.debt_ratio_by_year,
                    "roe_by_year": stmt.excluded.roe_by_year,
                    "fcf_per_share_by_year": stmt.excluded.fcf_per_share_by_year,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
            await session.execute(stmt)

        await session.commit()


async def _run(args: argparse.Namespace) -> None:
    # One event loop for the whole script — see screen_quality_stocks.py's comment on why
    # (splitting load/write across separate asyncio.run() calls left a stale asyncpg connection
    # bound to an already-closed loop).
    symbols = args.symbols.split(",") if args.symbols else None
    max_seconds = args.max_hours * 3600 if args.max_hours is not None else None

    metrics_cache = {} if args.refresh_cache else await _load_cache()
    logger.info("財報快取現有 %d 檔%s", len(metrics_cache), "（本次強制忽略，全部重抓）" if args.refresh_cache else "")

    start = time.monotonic()
    logger.info(
        "開始巴菲特選股篩選（universe_limit=%s, symbols=%s, max_hours=%s）",
        args.universe_limit, symbols, args.max_hours,
    )
    candidates = buffett_screening.screen_all(
        limit=args.limit,
        universe_limit=args.universe_limit,
        symbols=symbols,
        max_seconds=max_seconds,
        on_progress=_progress,
        metrics_cache=metrics_cache,
    )
    elapsed = time.monotonic() - start
    logger.info("篩選完成，耗時 %.1f 分鐘，符合巴菲特選股條件 %d 檔", elapsed / 60, len(candidates))

    for rank, c in enumerate(candidates, start=1):
        print(
            f"{rank:>2}. {c['symbol']} {c['name']}（{c['market']}）"
            f"負債比(1/3/5y)={c['debt_ratio_latest_pct']:.1f}/{c['debt_ratio_3y_avg_pct']:.1f}/{c['debt_ratio_5y_avg_pct']:.1f}% "
            f"ROE(1/3/5y)={c['roe_latest_pct']:.1f}/{c['roe_3y_avg_pct']:.1f}/{c['roe_5y_avg_pct']:.1f}% "
            f"每股FCF(1/3/5y)={c['fcf_per_share_latest']:.2f}/{c['fcf_per_share_3y_avg']:.2f}/{c['fcf_per_share_5y_avg']:.2f}"
        )

    if args.dry_run:
        logger.info("--dry-run：略過資料庫寫入（含財報快取）")
        return

    await _write_to_db(candidates, metrics_cache)
    logger.info(
        "已寫入 Neon（%d 筆符合巴菲特選股條件於 buffett_candidates，%d 筆財報快取於 company_buffett_cache）",
        len(candidates), len(metrics_cache),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="巴菲特選股清單批次篩選")
    parser.add_argument("--limit", type=int, default=80, help="輸出候選股數量上限（預設 80）")
    parser.add_argument("--universe-limit", type=int, default=None, help="限制掃描檔數（測試用）")
    parser.add_argument("--symbols", type=str, default=None, help="指定股票代號清單（逗號分隔，測試用，略過全市場清單）")
    parser.add_argument("--max-hours", type=float, default=None, help="時間預算（小時）：到時間就停止掃描，把目前為止的結果排名並寫入")
    parser.add_argument("--dry-run", action="store_true", help="不寫入資料庫（含財報快取），只印出結果")
    parser.add_argument("--refresh-cache", action="store_true", help="忽略現有財報快取，強制對每一檔重新呼叫 FinMind")
    args = parser.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
