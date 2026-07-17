# V4.0 部署備忘錄（overnight sentiment / 每日晨報）

本地已完成、尚未 push 的兩個 commit：
- `746c907` feat: implement V4.0 overnight sentiment MVP and morning session panel
- `f8b9cec` feat: implement V4.0 morning briefing center with snapshot caching and cron infrastructure

這份文件記錄：這兩個功能實際 push 並讓 Cloud Run 自動部署之後，有哪些雲端環境設定要先檢查，
以及稍早一次 Cloud Run 啟動崩潰（`create_tables` 逾時 → 503）的原因分析與程式防禦建議。

現有正式環境：Google Cloud Run 服務 `stock-backend`（專案 `stock-app-502313`，region
`asia-east1`），URL `https://stock-backend-884724294224.asia-east1.run.app`，GitHub 觸發自動部署
（`master` 分支，root dir `backend/`）。資料庫是 Neon Postgres（`ap-southeast-1`／Singapore，免費
方案）。詳見既有的 `stock-project-deployment-plan` / `stock-v32-fundamental-data-research` 記憶。

---

## 1. 08:30 排程 + yfinance 快照快取：Timeout／環境變數／硬體規格檢查清單

### 1.1 Timeout

| 項目 | 現況 / 風險 | 建議 |
|---|---|---|
| `/api/v1/morning-briefing/generate` 單次耗時 | 本地實測：正常幾秒，但曾出現一次 **約 2-3 分鐘**才回應（yfinance 的 `.info`，也就是 `regularMarketPrice` 的來源，比 `.history()` 慢且不穩定，是 yfinance 本身已知的特性，不是我們程式的 bug） | Cloud Run 服務的 **request timeout**（Console → 服務 → 編輯修訂版本 → 「要求逾時」）務必 **≥ 300 秒**，建議抓 540~600 秒的安全邊際，避免 yfinance 一慢就被 Cloud Run 自己先掐斷連線 |
| GitHub Actions 呼叫端 (`curl`) | **已修正**：`.github/workflows/morning-briefing.yml` 與新增的 `.github/workflows/backfill-analysis-returns.yml` 都已加上 `curl -sf --max-time 300 -X POST ...`，讓逾時行為明確可控，且與 Cloud Run 自己設定的 request timeout 對齊 | — |
| DB 連線 timeout（`connect_args={"timeout": 5}`，見 `backend/app/core/database.py`） | 5 秒對「Neon 免費方案 compute 因閒置被 autosuspend、需要冷啟動喚醒」這種情境可能太短——這正是下面第 2 節分析的崩潰主因之一 | 建議加大到 10~15 秒，或改用重試（見第 2.2 節的程式建議），不要只靠拉長單次 timeout |
| Cloud Run 冷啟動 × Neon 冷啟動 疊加 | 08:30 排程前一整晚很可能沒有任何流量，Cloud Run（若 min-instances=0）跟 Neon（免費方案本身也會 autosuspend）**很可能同時都處於閒置/暫停狀態**，兩者的喚醒延遲會疊加在同一次請求上 | 若不想額外付費，至少要確保 `create_tables` 有重試邏輯（見第 2.2 節）；若想徹底避免，可考慮把 Cloud Run 的 min-instances 設為 1（會持續產生費用，是取捨，不是必要項） |

### 1.2 環境變數

| 變數 | 目前應該的值 | 檢查重點 |
|---|---|---|
| `DATABASE_URL` | Neon 連線字串，格式 `postgresql+asyncpg://neondb_owner:***@ep-polished-boat-aoxz9ds6-pooler.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require`（注意：`ssl=require` 而非 Neon 主控台預設複製出來的 `sslmode=require`＋`channel_binding=require`，asyncpg 不認得後兩者） | **這是最容易在重新部署後「憑空消失」的一項**——本地的 `backend/.env` 不會被打包進 Cloud Run（`.dockerignore`／`.gitignore` 排除），必須直接在 Cloud Run 服務的環境變數設定裡手動填入；且 Cloud Run 每次由 Cloud Build 觸發器重新部署都是建立「新的修訂版本」，若部署流程本身沒有帶入這個環數，新版本可能不會自動繼承舊版本手動設過的值。**Push 前務必先到 Cloud Run Console 確認目前上線中的修訂版本這個變數確實存在且是 Neon 的值，不是程式碼裡的 localhost 預設值** |
| `CORS_ORIGINS` | `["https://stock-ruby-pi-69.vercel.app","https://stock.yusinlong.com","http://localhost:3000"]` | 與這次 08:30 排程無關——CORS 只作用於瀏覽器發出的請求，GitHub Actions 用 `curl` 直接打 API 不會被 CORS 擋下，不用把 CORS 誤判為排程失敗的原因 |
| `FINMIND_TOKEN` | 既有的 FinMind 權杖 | 這次 overnight sentiment／晨報功能本身不會呼叫 FinMind（只用 yfinance＋既有的 `chips.py`/`twse.py`），缺這個變數不會讓 `/generate` 失敗，但仍是既有功能（基本面分析頁籤等）需要的變數，一併確認還在 |
| 對外連線（egress） | 目前未設定 VPC Connector（預設允許對外連網） | 若未來加上 Serverless VPC Access 之類的網路限制，務必把 `query1.finance.yahoo.com`（yfinance 實際打的網域）、`www.twse.com.tw`、`api.finmindtrade.com` 都排除在限制之外，否則會複製一份 [[corporate-network-yfinance-ssl]] 記憶裡描述的辦公室網路阻擋情境到正式環境 |

### 1.3 硬體規格

- 目前 Cloud Run 服務的實際記憶體／CPU 配額沒有記錄在案——**push 前先到 Console 確認一次目前配額**，而不是假設它足夠。
- yfinance＋pandas 在同時處理 7 個總經 ticker＋波段股池每檔股票的籌碼面資料時會有短暫的記憶體尖峰；若之後在 Cloud Run 日誌看到 OOM-killed（記憶體不足被砍）的紀錄，優先調高記憶體配額，而不是急著改程式邏輯。
- Concurrency（每個執行個體同時處理的請求數）：這個排程本身流量極低（一天一次），不需要特別調整，但若擔心 `/generate` 這種長時間、耗網路 I/O 的請求跟其他使用者請求搶同一個執行個體資源，可以考慮把該服務的 concurrency 設低一點（例如 1）換取穩定度，非必要項。

---

## 2. `create_tables` 啟動崩潰分析（20:00 那次 503）

### 2.1 Traceback 的診斷

Traceback 的最後一段指到：

```
File "/app/app/main.py", line 36, in create_tables
    async with engine.begin() as conn:
```

對照目前程式碼（`backend/app/main.py` 第 35-41 行）：

```python
@app.on_event("startup")
async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

這段**完全沒有 try/except**。FastAPI／Starlette 的 `lifespan` 啟動流程規定：任何一個
`@app.on_event("startup")` handler 若丟出未捕捉的例外，整個 ASGI 應用程式的啟動流程會直接中止
——uvicorn 永遠不會進入「開始接受請求」的狀態。對 Cloud Run 而言，這代表容器啟動失敗，Cloud Run
會判定該修訂版本不健康，於是所有打進來的請求（包含 Cloud Scheduler／GitHub Actions 的呼叫）都拿到
**503 Service Unavailable**——這不是 API 邏輯錯誤，而是「容器根本沒有真正啟動起來」。

**最可能導致 `engine.begin()` 卡住/失敗的原因，依可能性排序：**

1. **Neon 免費方案的 compute autosuspend**：Neon 免費層在一段時間無連線後會把運算資源暫停，
   下一次連線需要先「喚醒」，官方文件說通常在 1 秒內，但偶爾會更久。20:00（離峰時段，前面可能已
   有一段時間沒人使用）加上 `connect_args={"timeout": 5}` 只給 5 秒——喚醒時間若超過 5 秒，
   asyncpg 的連線就會直接逾時失敗，而且沒有 try/except 接住，於是整個服務啟動崩潰。這是目前**最
   吻合「離峰時段才發生、平常不會發生」這個現象的解釋**。
2. **`DATABASE_URL` 在該次部署的修訂版本上遺失或錯誤**：如果當次部署的環境變數沒有正確帶入 Neon
   連線字串，`Settings.database_url` 會 fallback 成程式碼裡寫死的
   `postgresql+asyncpg://stock:stock@localhost:5432/stock`——Cloud Run 容器裡沒有本機 Postgres，
   這個連線必然失敗。可用「這次崩潰是不是剛好發生在一次新的部署之後」來反向驗證是否是這個原因。
3. **Neon 端的連線數/IP 限制**：目前沒有證據顯示 Neon 有開啟 IP allowlist，但如果之後手動開啟過
   這類限制又忘記把 Cloud Run 的對外 IP 排除，也會表現成同樣的連線逾時。

### 2.2 程式防禦建議：`create_tables` 加上 try/except（＋重試）

核心原則：**啟動階段的 DB 連線失敗，不應該讓整個服務死掉**。就算資料庫暫時連不上，服務仍應該
成功啟動、讓 `/api/v1/health` 這類不依賴 DB 的端點正常運作，只有真正需要 DB 的端點會在資料庫恢復
前回傳錯誤——這跟這個專案目前在 `chips.py`／`fundamentals.py`／`overnight_sentiment.py` 裡「資料
拿不到就回傳 `has_data: false`，而不是讓整支請求垮掉」的既有設計哲學是一致的，只是這裡要套用在
啟動流程本身。

建議把 `backend/app/main.py` 的 `create_tables` 改成：

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

DB_STARTUP_RETRY_ATTEMPTS = 3
DB_STARTUP_RETRY_DELAY_SECONDS = 3  # 給 Neon 免費方案從 autosuspend 喚醒的緩衝時間


@app.on_event("startup")
async def create_tables() -> None:
    for attempt in range(1, DB_STARTUP_RETRY_ATTEMPTS + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception:
            logger.exception(
                "create_tables 第 %d/%d 次嘗試失敗，資料庫可能尚在啟動或喚醒中",
                attempt, DB_STARTUP_RETRY_ATTEMPTS,
            )
            if attempt < DB_STARTUP_RETRY_ATTEMPTS:
                await asyncio.sleep(DB_STARTUP_RETRY_DELAY_SECONDS)

    logger.error("create_tables 最終仍失敗，服務照常啟動，但資料庫相關端點在資料庫恢復前都會回傳錯誤")
```

重點：
- **`try/except` 是必要項**——沒有它，任何一次暫時性的 DB 連線問題都會讓整個服務啟動失敗，而不
  只是那次操作失敗。
- **重試（重試 3 次、間隔 3 秒）是加分項**——直接對應第 2.1 節「Neon 冷啟動需要一點時間喚醒」的
  診斷，讓服務有機會撐過短暫的喚醒延遲，而不是重試次數用完後就放棄。
- 最終仍失敗時**只記錄錯誤、不重新拋出例外**，讓 uvicorn 正常進入服務狀態；之後可以用既有的
  `GET /api/v1/health/db` 端點（已確認可用，見 `stock-v32-fundamental-data-research` 記憶）主動
  確認資料庫是否真的恢復連線，而不是只看服務有沒有回應 200 就假設一切正常。
- **已套用**（2026-07-17）：`backend/app/main.py` 的 `create_tables` 已改成上述 try/except＋重試
  版本。本地驗證過兩種情況都沒問題：(1) 正常情況——DB 連得上時，第一次就成功並直接 `return`，
  完全不觸發重試/錯誤記錄，`/api/v1/health` 正常回應；(2) 邏輯上確認失敗路徑會重試 3 次、每次間隔
  3 秒，最終失敗只記錄錯誤、不會讓服務啟動崩潰（未在本地刻意模擬 DB 斷線來重現失敗路徑，因為本地
  DB 一直是可連線的——真正驗證失敗路徑的效果，要等下次正式環境真的遇到資料庫暫時連不上時才看得出
  來）。

---

## 3. Push 前的最後檢查順序（建議）

1. 到 Cloud Run Console 確認目前上線修訂版本的 `DATABASE_URL` 確實是 Neon 連線字串（第 1.2 節）。
2. 確認 Cloud Run 服務的 request timeout ≥ 300 秒（建議 540~600 秒，第 1.1 節）。
3. ~~套用第 2.2 節的 `create_tables` try/except＋重試~~ —— **已完成**（2026-07-17），降低單次 DB
   連線問題演變成整個服務起不來的機率。
4. Push 後，先手動用 GitHub Actions 頁面的 `workflow_dispatch` 分別觸發一次
   `.github/workflows/morning-briefing.yml`（確認 `POST /api/v1/morning-briefing/generate` 在正式
   環境能在合理時間內成功）與 `.github/workflows/backfill-analysis-returns.yml`（確認
   `POST /api/v1/verification/backfill` 正常運作），再放心讓兩者照各自的排程自動跑。
