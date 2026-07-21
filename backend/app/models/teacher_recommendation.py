"""老師建議清單——使用者的選股老師給的股票，額外附帶 ChatGPT/Gemini/Claude 三家 AI
針對「主要產業/長期評價/投資分類/AI受惠程度/波動程度/適合策略」的綜合評判（見
`teacher_recommendation_source.py`），跟這個 App 自己的技術面/基本面分析交叉比對，
產生一個獨立於老師原始排名之外的「進場時機」排名（見 `services/teacher_recommendations.py`）。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TeacherRecommendation(Base):
    __tablename__ = "teacher_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    teacher_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    main_industry: Mapped[str | None] = mapped_column(String, nullable=True)
    long_term_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    investment_category: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_benefit_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[str | None] = mapped_column(String, nullable=True)
    suitable_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
