import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.stocks import _pdf_response
from app.core.database import get_db
from app.models import TeacherRecommendation, TeacherRecommendationSource
from app.services import report, teacher_recommendations

router = APIRouter(prefix="/teacher-recommendations", tags=["teacher-recommendations"])


class TeacherRecommendationCreate(BaseModel):
    symbol: str
    name: str
    teacher_rank: int | None = None


class TeacherRecommendationUpdate(BaseModel):
    teacher_rank: int | None = None
    main_industry: str | None = None
    long_term_rating: float | None = None
    investment_category: str | None = None
    ai_benefit_rating: float | None = None
    volatility: str | None = None
    suitable_strategy: str | None = None


class RefreshReplyBody(BaseModel):
    chatgpt: str | None = None
    claude: str | None = None
    gemini: str | None = None


async def _load_rows(db: AsyncSession) -> list[TeacherRecommendation]:
    result = await db.execute(select(TeacherRecommendation).order_by(TeacherRecommendation.symbol))
    return list(result.scalars().all())


@router.get("")
async def list_teacher_recommendations(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await _load_rows(db)
    return {"recommendations": await teacher_recommendations.build_dashboard(rows)}


@router.post("", status_code=201)
async def create_teacher_recommendation(
    body: TeacherRecommendationCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    entry = TeacherRecommendation(
        symbol=body.symbol.strip().upper(), name=body.name, teacher_rank=body.teacher_rank
    )
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"股票代號 '{body.symbol}' 已在老師建議清單中") from exc
    await db.refresh(entry)
    return {"id": entry.id, "symbol": entry.symbol, "name": entry.name}


@router.patch("/{entry_id}")
async def update_teacher_recommendation(
    entry_id: int, body: TeacherRecommendationUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    entry = await db.get(TeacherRecommendation, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到此老師建議項目")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    if updates:
        entry.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "symbol": entry.symbol}


@router.delete("/{entry_id}", status_code=204)
async def delete_teacher_recommendation(entry_id: int, db: AsyncSession = Depends(get_db)) -> None:
    entry = await db.get(TeacherRecommendation, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="找不到此老師建議項目")
    await db.delete(entry)
    await db.commit()


@router.get("/refresh-prompt")
async def get_refresh_prompt(db: AsyncSession = Depends(get_db)) -> dict:
    rows = await _load_rows(db)
    if not rows:
        raise HTTPException(status_code=404, detail="老師建議清單目前是空的，請先新增股票")
    return {"prompt": teacher_recommendations.build_prompt(rows)}


async def _parse_all(db: AsyncSession, body: RefreshReplyBody) -> tuple[list[TeacherRecommendation], dict]:
    rows = await _load_rows(db)
    expected_symbols = {r.symbol for r in rows}
    texts = {"chatgpt": body.chatgpt, "claude": body.claude, "gemini": body.gemini}
    if not any(texts.values()):
        raise HTTPException(status_code=422, detail="請至少貼上一家 AI 的回答")

    parsed = {
        provider: teacher_recommendations.parse_provider_reply(provider, text, expected_symbols)
        if text and text.strip()
        else None
        for provider, text in texts.items()
    }
    return rows, parsed


@router.post("/refresh/parse")
async def parse_refresh(body: RefreshReplyBody, db: AsyncSession = Depends(get_db)) -> dict:
    rows, parsed = await _parse_all(db, body)
    changes = teacher_recommendations.compute_changes(rows, parsed)
    return {
        "providers": {
            p: ({"errors": r["errors"], "missing_symbols": r["missing_symbols"]} if r else None)
            for p, r in parsed.items()
        },
        "changes": changes,
    }


@router.post("/refresh/save")
async def save_refresh(body: RefreshReplyBody, db: AsyncSession = Depends(get_db)) -> dict:
    rows, parsed = await _parse_all(db, body)
    changes = teacher_recommendations.compute_changes(rows, parsed)
    rows_by_id = {r.id: r for r in rows}

    for change in changes:
        entry = rows_by_id[change["id"]]
        for field, value in change["reconciled"].items():
            setattr(entry, field, value)
        entry.updated_at = datetime.now(timezone.utc)

        for provider, parsed_row in change["sources"].items():
            if parsed_row is None:
                continue
            stmt = pg_insert(TeacherRecommendationSource).values(
                recommendation_id=change["id"],
                provider=provider,
                main_industry=parsed_row["main_industry"],
                long_term_rating=parsed_row["long_term_rating"],
                investment_category=parsed_row["investment_category"],
                ai_benefit_rating=parsed_row["ai_benefit_rating"],
                volatility=parsed_row["volatility"],
                suitable_strategy=parsed_row["suitable_strategy"],
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["recommendation_id", "provider"],
                set_={
                    "main_industry": stmt.excluded.main_industry,
                    "long_term_rating": stmt.excluded.long_term_rating,
                    "investment_category": stmt.excluded.investment_category,
                    "ai_benefit_rating": stmt.excluded.ai_benefit_rating,
                    "volatility": stmt.excluded.volatility,
                    "suitable_strategy": stmt.excluded.suitable_strategy,
                    "parsed_at": datetime.now(timezone.utc),
                },
            )
            await db.execute(stmt)

    await db.commit()
    return {
        "updated_count": len(changes),
        "providers": {
            p: ({"errors": r["errors"], "missing_symbols": r["missing_symbols"]} if r else None)
            for p, r in parsed.items()
        },
    }


@router.get("/report.pdf")
async def get_teacher_recommendations_report(db: AsyncSession = Depends(get_db)):
    rows = await _load_rows(db)
    dashboard = await teacher_recommendations.build_dashboard(rows)
    pdf_bytes = await asyncio.to_thread(report.render_teacher_recommendations_pdf, dashboard)
    return _pdf_response(pdf_bytes, "老師建議清單.pdf")
