from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import UserPortfolio
from app.services import portfolio

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class ParseRequest(BaseModel):
    text: str


class ImportRow(BaseModel):
    symbol: str
    name: str
    market: str
    shares: int
    cost_basis: float


class ImportRequest(BaseModel):
    rows: list[ImportRow]


@router.post("/parse")
async def parse_portfolio_text(body: ParseRequest) -> dict:
    """辨識貼上的庫存文字，回傳預覽用的解析結果——不寫入資料庫，供前端確認/手動修正後再匯入。"""
    return portfolio.parse_paste(body.text)


@router.post("/import")
async def import_portfolio(body: ImportRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """整批取代 `user_portfolio`——每次匯入視為完整的目前持股快照，不是增量的買賣紀錄。"""
    await db.execute(delete(UserPortfolio))
    for row in body.rows:
        db.add(UserPortfolio(
            symbol=row.symbol,
            name=row.name,
            market=row.market,
            shares=row.shares,
            cost_basis=row.cost_basis,
        ))
    await db.commit()
    return {"imported": len(body.rows)}


@router.get("")
async def get_portfolio_dashboard(db: AsyncSession = Depends(get_db)) -> dict:
    """即時計算目前庫存的盤點儀表板（技術面/基本面/財報狗清單/損益），不快取——
    跟首頁「開始 AI 掃描」同樣的即時運算慣例，持股數量通常遠小於全市場掃描，可接受。
    """
    result = await db.execute(select(UserPortfolio).order_by(UserPortfolio.symbol))
    rows = list(result.scalars().all())
    dashboard = await portfolio.build_dashboard(db, rows)
    return {"holdings": dashboard}
