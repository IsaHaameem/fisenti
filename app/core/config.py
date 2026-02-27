from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Dynamically get the absolute path to the root directory (where .env lives)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "Fisenti V1"
    DATABASE_URL: str
    
    # Phase 3: AI
    OPENAI_API_KEY: str
    
    # Phase 4: Market Data (Optional for now, we will use it later)
    
    # ADD THESE TWO LINES
    GROWW_API_KEY: str
    GROWW_API_SECRET: str
    GROWW_API_BASE_URL: str = "https://api.groww.in"
    
    # Phase 5: Telegram & Webhooks (Optional for now)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_SECRET_TOKEN: Optional[str] = None
    
    # Phase 6: Payments (Optional for now)
    RAZORPAY_KEY_ID: Optional[str] = None
    RAZORPAY_KEY_SECRET: Optional[str] = None
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = None

    # Point directly to the absolute path of the .env file
    model_config = SettingsConfigDict(env_file=str(ENV_FILE_PATH), extra="ignore")

settings = Settings()