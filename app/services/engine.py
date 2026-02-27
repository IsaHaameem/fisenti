import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from app.db.database import AsyncSessionLocal
from app.db.models import ClassifiedSignal, IntradaySignal, User, AlertLog
from app.services.telegram import format_macro_alert, format_intraday_alert, send_telegram_message

# Spec #4: Predefined Macro Relationships
SECTOR_MAP = {
    "Inflation": {"NIFTY IT": "Bearish", "NIFTY BANK": "Neutral", "NIFTY REALTY": "Bearish"},
    "Interest Rate": {"NIFTY BANK": "Bullish", "NIFTY AUTO": "Bearish", "NIFTY REALTY": "Bearish"},
    "Oil Prices": {"NIFTY ENERGY": "Bullish", "NIFTY AUTO": "Bearish"},
}

async def get_daily_count(session, user_id: int):
    """Checks alert count for Free tier limits (Spec #9)."""
    today = datetime.utcnow().date()
    res = await session.execute(
        select(func.count()).where(and_(AlertLog.user_id == user_id, func.date(AlertLog.sent_at) == today))
    )
    return res.scalar() or 0

async def downgrade_expired_trials():
    """Janitor job: Downgrades users after 30 days (Spec #10)."""
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        query = await session.execute(
            select(User).where(and_(User.subscription_status == "Trial", User.trial_end_date <= now))
        )
        expired_users = query.scalars().all()
        for user in expired_users:
            user.plan_type = "Free"
            user.subscription_status = "Active"
            asyncio.create_task(send_telegram_message(
                user.telegram_id, 
                "⚠️ <b>Trial Expired</b>\nYou have been moved to the Free tier (Delayed alerts, High severity only)."
            ))
        await session.commit()

async def run_alert_engine():
    """Main logic for matching Macro Signals with Intraday Confirmation."""
    async with AsyncSessionLocal() as session:
        users_query = await session.execute(select(User).where(User.subscription_status != "Inactive"))
        users = users_query.scalars().all()
        
        signals_query = await session.execute(
            select(ClassifiedSignal).where(ClassifiedSignal.created_at >= datetime.utcnow() - timedelta(hours=12))
        )
        signals = signals_query.scalars().all()

        for signal in signals:
            rules = SECTOR_MAP.get(signal.event_type, {})
            for user in users:
                # Deduplication
                already_sent = await session.execute(
                    select(AlertLog).where(and_(AlertLog.signal_id == signal.id, AlertLog.user_id == user.id))
                )
                if already_sent.scalar(): continue

                is_free = user.plan_type == "Free"
                if is_free:
                    if signal.severity != "High": continue
                    if (await get_daily_count(session, user.id)) >= 3: continue

                alert_text = None

                # High Severity = Immediate
                if signal.severity == "High":
                    # alert_text = format_macro_alert(signal.event_type, signal.headline, signal.severity, f"Bias: {signal.bias_direction}")
                    # Safely attempt to get the headline, fallback to the event type if missing
                    safe_headline = getattr(signal, 'headline', getattr(signal, 'event_text', f"New {signal.event_type} Data Detected"))
                    
                    alert_text = format_macro_alert(
                        event_type=signal.event_type, 
                        headline=safe_headline, 
                        severity=signal.severity, 
                        impact=f"Bias: {signal.bias_direction}"
                    )

                # Medium Severity = Needs Intraday Confirmation (Spec #6)
                elif signal.severity == "Medium" and not is_free:
                    for sector in signal.affected_sectors:
                        expected_bias = rules.get(sector, signal.bias_direction)
                        is_bearish = (expected_bias == "Bearish")
                        
                        confirmation = await session.execute(
                            select(IntradaySignal).where(and_(
                                IntradaySignal.sector == sector,
                                IntradaySignal.is_below_vwap == is_bearish,
                                IntradaySignal.triggered_at >= datetime.utcnow() - timedelta(hours=2)
                            )).limit(1)
                        )
                        confirm_data = confirmation.scalar()

                        if confirm_data:
                            alert_text = format_intraday_alert(sector, "Below" if is_bearish else "Above", confirm_data.volume_multiplier, expected_bias)
                            break

                if alert_text:
                    await send_telegram_message(user.telegram_id, alert_text)
                    session.add(AlertLog(user_id=user.id, signal_id=signal.id, alert_text=alert_text))
                    await session.commit()