import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.api.webhooks import router as webhook_router
from app.services.engine import run_alert_engine, downgrade_expired_trials
from app.core.config import settings

from app.services.ingestion import poll_rss_feeds
from app.services.market import check_intraday_confirmation

# Initialize the native async scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print(f"Starting {settings.PROJECT_NAME} Engine...")
    
    # We can pass the native async functions directly
    scheduler.add_job(
        poll_rss_feeds, 
        'interval', 
        seconds=15, 
        id='rss_ingestion_job',
        replace_existing=True
    )
    
    scheduler.add_job(
        check_intraday_confirmation, 
        'interval', 
        seconds=15, 
        id='market_data_job',
        replace_existing=True
    )
    
    scheduler.add_job(
        run_alert_engine, 
        'interval', 
        seconds=15, 
        id='alert_engine_job',
        replace_existing=True
    )
    
    scheduler.add_job(
        downgrade_expired_trials, 
        'interval', 
        hours=1, 
        id='trial_janitor_job',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ Background Scheduler started cleanly.")
    
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

# Health check route
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