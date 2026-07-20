"""一次性 migration：為既有的 analysis_history 資料表補上 signal_codes 欄位（V3.6 第二支柱）。

這個專案還沒有導入 Alembic（見 memory 'stock-project-step-progress' Step 10/11），
`Base.metadata.create_all` 只會建立「不存在的資料表」，不會幫既有資料表加欄位——
所以新增 `AnalysisHistory.signal_codes` 欄位後，Neon 上既有的資料列需要手動
ALTER TABLE，而不是單純重跑 create_all。與 `migrate_add_stock_name.py` 同一套模式，
但這欄位沒有回填步驟——舊資料列當天實際觸發哪些訊號 code 已經無法從
`layer_directions`（只到 layer 粒度）反推，維持 NULL 是永久狀態，不是待補。

執行方式（於 backend/ 目錄下）：
    python scripts/migrate_add_signal_codes.py

冪等：欄位已存在時 ALTER TABLE 會被跳過。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS signal_codes JSON"))
    print("已確認 signal_codes 欄位存在")


if __name__ == "__main__":
    asyncio.run(main())
