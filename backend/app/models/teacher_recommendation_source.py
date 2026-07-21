"""三家 AI（chatgpt/gemini/claude）針對同一檔「老師建議」股票各自給出的原始評判——
每次重新整理都是整批取代（同一 `(recommendation_id, provider)` upsert），不保留歷史回合，
只保留「最新一輪」每家的說法，用來在 `main_industry`/`investment_category` 等欄位三家
意見不一致時，讓使用者看得到「為什麼最後採用這個值」。
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TeacherRecommendationSource(Base):
    __tablename__ = "teacher_recommendation_sources"
    __table_args__ = (UniqueConstraint("recommendation_id", "provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teacher_recommendations.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)  # "chatgpt" / "gemini" / "claude"
    main_industry: Mapped[str | None] = mapped_column(String, nullable=True)
    long_term_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    investment_category: Mapped[str | None] = mapped_column(String, nullable=True)
    ai_benefit_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility: Mapped[str | None] = mapped_column(String, nullable=True)
    suitable_strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
