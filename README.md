# Jerry AI Stock Analyst Pro V3.0

AI Technical Analysis Decision Engine — 協助投資人提高決策品質，而非預測股價。

## 架構

```
stock/
├── frontend/    Next.js + TypeScript + Tailwind CSS + shadcn/ui + TradingView Lightweight Charts
├── backend/     FastAPI + SQLAlchemy (async) + PostgreSQL + Redis
└── docker-compose.yml   本地開發用 PostgreSQL + Redis
```

## 本地開發

### 1. 啟動 PostgreSQL / Redis（需先安裝並啟動 Docker Desktop）

```
docker compose up -d
```

### 2. Backend

```
cd backend
cp .env.example .env
./.venv/Scripts/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

- API 文件: http://localhost:8000/docs
- Health check: http://localhost:8000/api/v1/health

### 3. Frontend

```
cd frontend
npm run dev
```

- 網站: http://localhost:3000
