"""一次性 migration：為既有的 analysis_history 資料表補上 stock_name 欄位。

這個專案還沒有導入 Alembic（見 memory 'stock-project-step-progress' Step 10/11），
`Base.metadata.create_all` 只會建立「不存在的資料表」，不會幫既有資料表加欄位——
所以新增 `AnalysisHistory.stock_name` 欄位後，Neon 上既有的資料列需要手動
ALTER TABLE + 回填，而不是單純重跑 create_all。

執行方式（於 backend/ 目錄下）：
    python scripts/migrate_add_stock_name.py

冪等：欄位已存在時 ALTER TABLE 會被跳過；stock_name 已經有值的資料列不會被覆蓋。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.services import company  # noqa: E402


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS stock_name VARCHAR"))
    print("已確認 stock_name 欄位存在")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT DISTINCT stock_code FROM analysis_history WHERE stock_name IS NULL")
        )
        codes = [row[0] for row in result.fetchall()]
        print(f"待補上名稱的股票代號：{codes}")

        for code in codes:
            info = company.get_company_info(code)
            name = info["name"] if info else code
            await session.execute(
                text("UPDATE analysis_history SET stock_name = :name WHERE stock_code = :code AND stock_name IS NULL"),
                {"name": name, "code": code},
            )
            print(f"  {code} -> {name}")

        await session.commit()

    print("migration 完成")


if __name__ == "__main__":
    asyncio.run(main())
