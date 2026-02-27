import nest_asyncio
nest_asyncio.apply()
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.api.webhooks import router as webhook_router
# from app.services.engine import run_alert_engine
from app.services.engine import run_alert_engine, downgrade_expired_trials
# Import your settings
from app.core.config import settings

# Import the background tasks
from app.services.ingestion import poll_rss_feeds
from app.services.market import check_intraday_confirmation

# Initialize the scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print(f"Starting {settings.PROJECT_NAME} Engine...")
    
    # Job 1: RSS Ingestion (Runs every 15 seconds)
    scheduler.add_job(
        poll_rss_feeds, 
        'interval', 
        seconds=15, 
        id='rss_ingestion_job',
        replace_existing=True
    )
    
    # Job 2: Market Data Polling (Runs every 15 seconds)
    scheduler.add_job(
        check_intraday_confirmation, 
        'interval', 
        seconds=15, 
        id='market_data_job',
        replace_existing=True
    )
    # Job 3: Alert Engine & Matcher (Runs every 15 seconds)
    scheduler.add_job(
        run_alert_engine, 
        'interval', 
        seconds=15, 
        id='alert_engine_job',
        replace_existing=True
    )
    # Job 4: Trial Janitor (Runs once every hour)
    scheduler.add_job(
        downgrade_expired_trials, 
        'interval', 
        hours=1, 
        id='trial_janitor_job',
        replace_existing=True
    )
    
    scheduler.start()
    print("✅ Background Scheduler started.")
    
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
    return {"message": "Fisenti Intelligence Engine is running."}