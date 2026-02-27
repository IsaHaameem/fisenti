import hmac
import hashlib
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Header, HTTPException
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.services.telegram import dp, bot
from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import User, Subscription
from app.services.telegram import format_macro_alert, format_intraday_alert

router = APIRouter()

# ==========================================
# 1. TELEGRAM BOT COMMAND HANDLERS
# ==========================================

@dp.message(lambda message: message.text == "/start")
async def start_command_handler(message):
    """Handles the /start command and grants the 30-Day Pro Trial."""
    telegram_id = str(message.from_user.id)
    now = datetime.utcnow()
    trial_end = now + timedelta(days=30)
    
    async with AsyncSessionLocal() as session:
        # Insert user with Pro plan and Trial status. If exists, do nothing.
        stmt = insert(User).values(
            telegram_id=telegram_id,
            plan_type="Pro", # Give full access during trial
            subscription_status="Trial",
            trial_start_date=now,
            trial_end_date=trial_end
        ).on_conflict_do_nothing(index_elements=['telegram_id'])
        
        await session.execute(stmt)
        await session.commit()

    welcome_text = (
        "📊 <b>Welcome to Fisenti V1</b>\n\n"
        "Your <b>30-Day Pro Trial</b> has been activated! 🚀\n"
        "You will receive real-time Macro & Intraday Confluence alerts.\n\n"
        "<i>Waiting for market signals...</i>"
    )
    await message.answer(welcome_text)


# ==========================================
# 2. TELEGRAM WEBHOOK ROUTE
# ==========================================

@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    """This endpoint receives updates directly from Telegram."""
    
    # Verify the request is actually from Telegram
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Parse the incoming JSON into an aiogram Update object
    update_data = await request.json()
    update = Update(**update_data)
    
    # Feed the update into our bot dispatcher
    await dp.feed_update(bot, update)
    
    return {"status": "ok"}


# ==========================================
# 3. RAZORPAY WEBHOOK ROUTE
# ==========================================

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request, 
    x_razorpay_signature: str = Header(None)
):
    """Listens for Razorpay subscription payments and cancellations."""
    body = await request.body()
    
    # 1. Verify Signature to ensure it's from Razorpay
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay secret not configured")
        
    expected_sig = hmac.new(
        bytes(settings.RAZORPAY_WEBHOOK_SECRET, 'utf-8'),
        msg=body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_sig, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
        
    payload = json.loads(body)
    event = payload.get("event")
    
    # 2. Extract Data (Assuming you pass telegram_id in Razorpay 'notes' when creating the payment link)
    sub_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})
    telegram_id = sub_entity.get("notes", {}).get("telegram_id")
    razorpay_sub_id = sub_entity.get("id")
    
    if not telegram_id:
        return {"status": "ignored", "reason": "No telegram_id in notes"}

    # 3. Handle Subscription Events
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == str(telegram_id)))
        user = result.scalar_one_or_none()
        
        if not user:
            return {"status": "ignored", "reason": "User not found"}

        if event in ["subscription.charged", "subscription.authenticated"]:
            # Upgrade user to Pro
            user.plan_type = "Pro"
            user.subscription_status = "Active"
            
            # Upsert Subscription Record
            stmt = insert(Subscription).values(
                user_id=user.id,
                razorpay_sub_id=razorpay_sub_id,
                status="Active"
            ).on_conflict_do_update(
                index_elements=['razorpay_sub_id'],
                set_={'status': "Active"}
            )
            await session.execute(stmt)
            await session.commit()
            
            await bot.send_message(
                chat_id=telegram_id, 
                text="✅ <b>Payment Successful!</b>\nYou are now officially on Fisenti Pro. Real-time alerts are active."
            )

        elif event in ["subscription.cancelled", "subscription.halted"]:
            # Downgrade user to Free
            user.plan_type = "Free"
            user.subscription_status = "Inactive"
            await session.commit()
            
            await bot.send_message(
                chat_id=telegram_id, 
                text="⚠️ <b>Subscription Ended</b>\nYou have been downgraded to the Free tier. Alerts will be delayed."
            )
            
    return {"status": "ok"}
# @dp.message(lambda message: message.text == "/test_alert")
# async def test_alert_command(message):
#     """Sends a dummy alert to verify Telegram formatting."""
    
#     # Test Macro Alert
#     macro_text = format_macro_alert(
#         event_type="Inflation",
#         headline="US CPI Data Shows Unexpected Spike to 4.5%",
#         severity="High",
#         impact="Bearish for NIFTY IT, Bullish for NIFTY BANK"
#     )
#     await message.answer(macro_text)
    
#     # Test Intraday Alert
#     intraday_text = format_intraday_alert(
#         sector="NIFTY IT",
#         direction="Below",
#         volume_multiplier=1.8,
#         expected_bias="Bearish"
#     )
#     await message.answer(intraday_text)