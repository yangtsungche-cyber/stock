"""一次性 migration：為既有的 `user_portfolio` 資料表加上 `owner` 欄位, 並把主鍵從單純
`symbol` 改成複合鍵 `(owner, symbol)` —— 不同家人（我/太太/女兒）可能持有同一檔股票,
單靠 `symbol` 已經無法唯一識別一筆持股。

這個專案還沒有導入 Alembic, `Base.metadata.create_all` 只會建立「不存在的資料表」,
不會幫既有資料表加欄位或改主鍵, 所以需要手動 ALTER TABLE, 而不是單純重跑 create_all
（同 `migrate_add_stock_name.py` 的慣例）。

執行方式（於 backend/ 目錄下）：
    python scripts/migrate_add_portfolio_owner.py

冪等：欄位/主鍵已符合目標狀態時, 對應的 ALTER 會被跳過。既有資料列一律回填為 owner='我'
（這個專案原本就是單一持股快照, 全部視為使用者本人的持股）。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402

DEFAULT_OWNER = "我"


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE user_portfolio ADD COLUMN IF NOT EXISTS owner VARCHAR"))
        await conn.execute(
            text("UPDATE user_portfolio SET owner = :owner WHERE owner IS NULL"),
            {"owner": DEFAULT_OWNER},
        )
        await conn.execute(text("ALTER TABLE user_portfolio ALTER COLUMN owner SET NOT NULL"))
        await conn.execute(text("ALTER TABLE user_portfolio DROP CONSTRAINT IF EXISTS user_portfolio_pkey"))
        await conn.execute(text("ALTER TABLE user_portfolio ADD PRIMARY KEY (owner, symbol)"))
    print(f"已確認 owner 欄位存在（既有資料列回填為「{DEFAULT_OWNER}」）、主鍵已改為 (owner, symbol)")


if __name__ == "__main__":
    asyncio.run(main())
