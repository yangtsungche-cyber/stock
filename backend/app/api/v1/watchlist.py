from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import StockWatchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

Category = Literal["核心", "波段", "觀察"]


class WatchlistCreate(BaseModel):
    stock_code: str
    stock_name: str
    category: Category
    note: str | None = None


class WatchlistUpdate(BaseModel):
    category: Category | None = None
    enabled: bool | None = None
    note: str | None = None


class WatchlistOut(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    category: str
    enabled: bool
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[WatchlistOut])
async def list_watchlist(db: AsyncSession = Depends(get_db)) -> list[StockWatchlist]:
    result = await db.execute(select(StockWatchlist).order_by(StockWatchlist.category, StockWatchlist.stock_code))
    return list(result.scalars().all())


@router.post("", response_model=WatchlistOut, status_code=201)
async def create_watchlist_entry(body: WatchlistCreate, db: AsyncSession = Depends(get_db)) -> StockWatchlist:
    entry = StockWatchlist(
        stock_code=body.stock_code.strip().upper(),
        stock_name=body.stock_name,
        category=body.category,
        note=body.note,
    )
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"股票代號 '{body.stock_code}' 已在自選股池中") from exc
    await db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=WatchlistOut)
async def update_watchlist_entry(
    entry_id: int, body: WatchlistUpdate, db: AsyncSession = Depends(get_db)
) -> StockWatchlist:
    entry = await db.get(StockWatchlist, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到此自選股項目")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_watchlist_entry(entry_id: int, db: AsyncSession = Depends(get_db)) -> None:
    entry = await db.get(StockWatchlist, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到此自選股項目")
    await db.delete(entry)
    await db.commit()
