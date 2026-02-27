from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.core.config import settings

# Initialize the bot with HTML parsing for clean formatting
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Dispatcher handles incoming updates (like /start commands)
dp = Dispatcher()

def format_macro_alert(event_type: str, headline: str, severity: str, impact: str) -> str:
    """
    Formats the raw AI output into a minimal, institutional alert.
    Example:
    US CPI: 4.2% (Exp 3.8%)
    Severity: High
    Impact: Bearish IT
    """
    return f"<b>{event_type}</b>\n{headline}\n\nSeverity: {severity}\nImpact: {impact}"

def format_intraday_alert(sector: str, vwap_status: str, vol_multiplier: float, bias: str) -> str:
    """
    Formats the intraday confirmation alert.
    Example:
    IT Sector
    Below VWAP
    Volume 1.8x
    🔥 Intraday Bearish Bias Active
    """
    icon = "🔥" if bias.lower() == "bearish" else "🚀"
    return (
        f"<b>{sector}</b>\n"
        f"{vwap_status} VWAP\n"
        f"Volume {vol_multiplier:.1f}x\n\n"
        f"{icon} Intraday {bias} Bias Active"
    )

async def send_telegram_message(telegram_id: str, text: str):
    """Sends a message to a specific user."""
    try:
        await bot.send_message(chat_id=telegram_id, text=text)
    except Exception as e:
        print(f"❌ Failed to send Telegram message to {telegram_id}: {e}")