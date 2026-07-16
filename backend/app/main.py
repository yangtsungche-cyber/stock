from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.scan import router as scan_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.verification import router as verification_router
from app.api.v1.watchlist import router as watchlist_router
from app.core.config import get_settings
from app.core.database import Base, engine

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(scan_router, prefix="/api/v1")
app.include_router(stocks_router, prefix="/api/v1")
app.include_router(verification_router, prefix="/api/v1")
app.include_router(watchlist_router, prefix="/api/v1")


@app.on_event("startup")
async def create_tables() -> None:
    # No Alembic migrations yet — fine for this project's current scale, see
    # memory 'stock-project-step-progress' Step 10. Revisit once schema
    # changes need to preserve existing data instead of just adding tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
