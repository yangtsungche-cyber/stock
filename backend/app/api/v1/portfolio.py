from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import PortfolioAnnotation, PortfolioValueSnapshot, UserPortfolio
from app.services import portfolio

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

DEFAULT_OWNER = "我"


class ParseRequest(BaseModel):
    text: str


class ImportRow(BaseModel):
    symbol: str
    name: str
    market: str
    shares: int
    cost_basis: float


class ImportRequest(BaseModel):
    owner: str = DEFAULT_OWNER
    rows: list[ImportRow]


class AnnotationRequest(BaseModel):
    date: date_type
    note: str


@router.post("/parse")
async def parse_portfolio_text(body: ParseRequest) -> dict:
    """辨識貼上的庫存文字，回傳預覽用的解析結果——不寫入資料庫，供前端確認/手動修正後再匯入。"""
    return portfolio.parse_paste(body.text)


@router.post("/import")
async def import_portfolio(body: ImportRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """整批取代**該成員**（我/太太/女兒...）的持股——每次匯入視為該成員完整的目前持股快照，
    不是增量的買賣紀錄，也不影響其他成員的持股資料。
    """
    await db.execute(delete(UserPortfolio).where(UserPortfolio.owner == body.owner))
    for row in body.rows:
        db.add(UserPortfolio(
            owner=body.owner,
            symbol=row.symbol,
            name=row.name,
            market=row.market,
            shares=row.shares,
            cost_basis=row.cost_basis,
        ))
    await db.commit()
    return {"imported": len(body.rows)}


@router.get("/summary")
async def get_portfolio_summary(db: AsyncSession = Depends(get_db)) -> dict:
    """各成員（我/太太/女兒...）+ 總計的市值/損益/損益%/預估股利概況——用 bulk 快照資料
    快速算出，不跑逐檔的技術面/基本面即時分析，所以幾秒內就能載入（跟下面 `get_portfolio_dashboard`
    的「數分鐘」形成對比，是刻意分成兩個不同成本層級的端點）。
    """
    result = await db.execute(select(UserPortfolio))
    rows = list(result.scalars().all())
    return await portfolio.build_summary(rows)


@router.get("")
async def get_portfolio_dashboard(owner: str = DEFAULT_OWNER, db: AsyncSession = Depends(get_db)) -> dict:
    """即時計算**該成員**目前庫存的盤點儀表板（技術面/基本面/財報狗清單/損益），不快取——
    跟首頁「開始 AI 掃描」同樣的即時運算慣例，持股數量通常遠小於全市場掃描，可接受。
    """
    result = await db.execute(
        select(UserPortfolio).where(UserPortfolio.owner == owner).order_by(UserPortfolio.symbol)
    )
    rows = list(result.scalars().all())
    dashboard = await portfolio.build_dashboard(db, rows)
    return {"holdings": dashboard}


@router.post("/snapshot")
async def create_portfolio_snapshot(db: AsyncSession = Depends(get_db)) -> dict:
    """把今天每個成員的市值寫入 `portfolio_value_snapshots`——由每日排程呼叫（見
    `.github/workflows/portfolio-snapshot.yml`），也可以手動觸發補一筆。同一天重複呼叫會
    覆蓋當天那筆（upsert on (date, owner)），不會累積出重複資料。
    """
    result = await db.execute(select(UserPortfolio))
    rows = list(result.scalars().all())
    values_by_owner = await portfolio.snapshot_owner_values(rows)

    today = datetime.now(timezone.utc).date()
    for owner, market_value in values_by_owner.items():
        stmt = pg_insert(PortfolioValueSnapshot).values(date=today, owner=owner, market_value=market_value)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "owner"], set_={"market_value": stmt.excluded.market_value}
        )
        await db.execute(stmt)
    await db.commit()
    return {"date": today.isoformat(), "owners": values_by_owner}


@router.get("/history")
async def get_portfolio_history(db: AsyncSession = Depends(get_db)) -> dict:
    """市值歷史走勢圖用的時間序列——依日期把各成員市值攤平成一列, 並附上「我+太太」的
    合計欄位（前端 4 條線裡的第一條）。"""
    result = await db.execute(select(PortfolioValueSnapshot).order_by(PortfolioValueSnapshot.date))
    rows = list(result.scalars().all())

    by_date: dict[date_type, dict[str, float]] = {}
    for row in rows:
        by_date.setdefault(row.date, {})[row.owner] = row.market_value

    points = []
    for d, values in sorted(by_date.items()):
        me = values.get("我")
        spouse = values.get("太太")
        combined = (me or 0) + (spouse or 0) if (me is not None or spouse is not None) else None
        points.append({
            "date": d.isoformat(),
            "我": me,
            "太太": spouse,
            "女兒": values.get("女兒"),
            "我+太太": combined,
        })
    return {"points": points}


@router.get("/annotations")
async def list_portfolio_annotations(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(PortfolioAnnotation).order_by(PortfolioAnnotation.date))
    rows = list(result.scalars().all())
    return {
        "annotations": [
            {"id": r.id, "date": r.date.isoformat(), "note": r.note} for r in rows
        ]
    }


@router.post("/annotations")
async def create_portfolio_annotation(body: AnnotationRequest, db: AsyncSession = Depends(get_db)) -> dict:
    row = PortfolioAnnotation(date=body.date, note=body.note)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "date": row.date.isoformat(), "note": row.note}


@router.delete("/annotations/{annotation_id}")
async def delete_portfolio_annotation(annotation_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(PortfolioAnnotation).where(PortfolioAnnotation.id == annotation_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到這筆註記")
    await db.delete(row)
    await db.commit()
    return {"deleted": annotation_id}
