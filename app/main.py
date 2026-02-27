import nest_asyncio
nest_asyncio.apply()

import asyncio
import sniffio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api.webhooks import router as webhook_router
from app.services.engine import run_alert_engine, downgrade_expired_trials
from app.core.config import settings

from app.services.ingestion import poll_rss_feeds
from app.services.market import check_intraday_confirmation

# --- THE FIX: Bulletproof Task Wrappers ---
# These functions force the async context so HTTPX and AsyncPG don't crash

async def safe_poll_rss_feeds():
    """Forces the RSS feed into a strict asyncio Task context."""
    sniffio.current_async_library_cvar.set("asyncio")
    await asyncio.create_task(poll_rss_feeds())

async def safe_check_intraday_confirmation():
    """Forces the Market Data polling into a strict asyncio Task context."""
    sniffio.current_async_library_cvar.set("asyncio")
    await asyncio.create_task(check_intraday_confirmation())

async def safe_run_alert_engine():
    """Forces the Engine into a strict asyncio Task context."""
    sniffio.current_async_library_cvar.set("asyncio")
    await asyncio.create_task(run_alert_engine())

async def safe_downgrade_expired_trials():
    """Forces the Janitor job into a strict asyncio Task context."""
    sniffio.current_async_library_cvar.set("asyncio")
    await asyncio.create_task(downgrade_expired_trials())


# Initialize the scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print(f"Starting {settings.PROJECT_NAME} Engine...")
    
    # Job 1: RSS Ingestion (Runs every 15 seconds)
    scheduler.add_job(
        safe_poll_rss_feeds, 
        'interval', 
        seconds=15, 
        id='rss_ingestion_job',
        replace_existing=True
    )
    
    # Job 2: Market Data Polling (Runs every 15 seconds)
    scheduler.add_job(
        safe_check_intraday_confirmation, 
        'interval', 
        seconds=15, 
        id='market_data_job',
        replace_existing=True
    )
    
    # Job 3: Alert Engine & Matcher (Runs every 15 seconds)
    scheduler.add_job(
        safe_run_alert_engine, 
        'interval', 
        seconds=15, 
        id='alert_engine_job',
        replace_existing=True
    )
    
    # Job 4: Trial Janitor (Runs once every hour)
    scheduler.add_job(
        safe_downgrade_expired_trials, 
        'interval', 
        hours=1, 
        id='trial_janitor_job',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ Background Scheduler started with strict Task contexts.")
    
    yield # App runs here
    
    # --- Shutdown Logic ---
    print("Shutting down Engine...")
    scheduler.shutdown()
    print("🛑 Scheduler stopped.")

# Initialize FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan
)

# Health check route (Required for Render deployment)
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "engine": settings.PROJECT_NAME,
        "scheduler_running": scheduler.running
    }

app.include_router(webhook_router, prefix="/api/webhooks", tags=["Webhooks"])

@app.get("/")
async def root():
    return {"message": f"{settings.PROJECT_NAME} Intelligence Engine is running."}