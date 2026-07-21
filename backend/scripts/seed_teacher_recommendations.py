"""一次性種子腳本：把 `D:\\LONG.XLSX`（老師建議清單，經 ChatGPT 補充六項描述欄位）寫入
teacher_recommendations + teacher_recommendation_sources（provider="chatgpt"，因為這些欄位
本來就是 ChatGPT 產生的第一輪答案）。

執行方式（於 backend/ 目錄下）：
    python scripts/seed_teacher_recommendations.py

Idempotent：已存在的 symbol 會被略過，不會重複插入或覆蓋使用者後續的手動編輯/AI 重新整理結果。
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import TeacherRecommendation, TeacherRecommendationSource  # noqa: E402
from app.services import company  # noqa: E402


def _stars(s: str) -> float:
    return s.count("★") + (0.5 if "☆" in s else 0.0)


# (teacher_rank, symbol, name, main_industry, long_term_rating(★), investment_category,
#  ai_benefit_rating(★), volatility, suitable_strategy) —— 直接照 D:\LONG.XLSX 的 25 列。
SEED = [
    (1, "3131", "弘塑", "半導體設備", "★★★★★", "AI成長", "★★★★★", "高", "波段"),
    (2, "7734", "印能科技", "半導體設備", "★★★★★", "AI成長", "★★★★★", "高", "波段"),
    (3, "5289", "宜鼎", "工業電腦/AI記憶體", "★★★★★", "退休核心", "★★★★★", "中", "長抱"),
    (4, "3023", "信邦", "電子零組件", "★★★★☆", "退休核心", "★★★★", "中低", "長抱"),
    (5, "8147", "正淩", "AI伺服器連接器", "★★★★", "退休核心", "★★★★", "中", "長抱"),
    (6, "7853", "政美應用", "半導體材料", "★★★★", "AI成長", "★★★★", "中高", "波段"),
    (7, "2233", "宇隆", "精密機械", "★★★☆", "退休核心", "★★★", "中", "長抱"),
    (8, "7721", "微程式", "電子支付/智慧設備", "★★★", "題材股", "★★★", "中高", "短線"),
    (9, "4949", "有成精密", "太陽能/能源", "★★☆", "題材股", "★★", "高", "短線"),
    (10, "7799", "禾榮科", "生技醫療", "★★", "題材股", "★", "高", "觀察"),
    (None, "5536", "聖暉", "無塵室/廠務工程", "★★★★★", "退休核心", "★★★★★", "中", "長抱"),
    (None, "6613", "朋億", "廠務供應系統", "★★★★★", "退休核心", "★★★★★", "中", "長抱"),
    (None, "7703", "銳澤", "半導體氣體供應", "★★★★★", "AI成長", "★★★★★", "高", "波段"),
    (None, "3037", "欣興", "ABF載板", "★★★★", "退休核心", "★★★★", "中", "長抱"),
    (None, "6239", "力成", "封測", "★★★★", "退休核心", "★★★★", "中", "長抱"),
    (None, "8091", "翔名", "半導體耗材", "★★★★", "AI成長", "★★★★", "中高", "波段"),
    (None, "8027", "鈦昇", "半導體設備", "★★★★", "AI成長", "★★★★", "中高", "波段"),
    (None, "1595", "川寶", "PCB設備", "★★★☆", "AI成長", "★★★", "中高", "波段"),
    (None, "8112", "至上", "IC通路", "★★★☆", "觀察", "★★★", "中", "觀察"),
    (None, "6189", "豐藝", "IC通路", "★★★☆", "觀察", "★★★", "中", "觀察"),
    (None, "6940", "格斯", "電池", "★★★", "題材股", "★★★", "高", "短線"),
    (None, "3707", "漢磊", "功率半導體", "★★☆", "題材股", "★★★", "高", "短線"),
    (None, "2441", "超豐", "封測", "★★☆", "題材股", "★★", "中", "短線"),
    (None, "1711", "永光", "化工材料", "★★☆", "題材股", "★★", "中", "觀察"),
    (None, "4114", "健喬", "生技製藥", "★★", "觀察", "★", "高", "觀察"),
]


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existing = set((await session.execute(select(TeacherRecommendation.symbol))).scalars().all())
        added = 0
        for teacher_rank, symbol, name, industry, long_term, category, ai_benefit, volatility, strategy in SEED:
            if symbol in existing:
                continue
            info = company.get_company_info(symbol)
            resolved_name = info["name"] if info else name

            entry = TeacherRecommendation(
                symbol=symbol,
                name=resolved_name,
                teacher_rank=teacher_rank,
                main_industry=industry,
                long_term_rating=_stars(long_term),
                investment_category=category,
                ai_benefit_rating=_stars(ai_benefit),
                volatility=volatility,
                suitable_strategy=strategy,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            await session.flush()  # need entry.id before writing the source row

            session.add(TeacherRecommendationSource(
                recommendation_id=entry.id,
                provider="chatgpt",
                main_industry=industry,
                long_term_rating=_stars(long_term),
                investment_category=category,
                ai_benefit_rating=_stars(ai_benefit),
                volatility=volatility,
                suitable_strategy=strategy,
            ))
            added += 1

        await session.commit()
        print(f"新增 {added} 筆，略過 {len(SEED) - added} 筆（已存在）")


if __name__ == "__main__":
    asyncio.run(main())
