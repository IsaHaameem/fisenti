from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum

class Base(DeclarativeBase):
    pass

# --- Enums ---
class SeverityEnum(str, enum.Enum):
    High = "High"
    Medium = "Medium"
    Low = "Low"

class BiasEnum(str, enum.Enum):
    Bullish = "Bullish"
    Bearish = "Bearish"
    Neutral = "Neutral"

class TimeHorizonEnum(str, enum.Enum):
    Intraday = "Intraday"
    Swing = "Swing"

class PlanTypeEnum(str, enum.Enum):
    Free = "Free"
    Starter = "Starter"
    Pro = "Pro"

class SubStatusEnum(str, enum.Enum):
    Active = "Active"
    Inactive = "Inactive"
    Trial = "Trial"

# --- Models ---
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    telegram_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    plan_type: Mapped[PlanTypeEnum] = mapped_column(Enum(PlanTypeEnum), default=PlanTypeEnum.Free)
    subscription_status: Mapped[SubStatusEnum] = mapped_column(Enum(SubStatusEnum), default=SubStatusEnum.Inactive)
    trial_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String) # e.g., "Google News", "RBI"
    headline: Mapped[str] = mapped_column(String, unique=True) # Used for deduplication
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    url: Mapped[str] = mapped_column(String)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class ClassifiedSignal(Base):
    __tablename__ = "classified_signals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String)
    severity: Mapped[SeverityEnum] = mapped_column(Enum(SeverityEnum))
    region: Mapped[str] = mapped_column(String)
    affected_sectors: Mapped[List[str]] = mapped_column(JSON) # Stores list like ["IT", "Banking"]
    bias_direction: Mapped[BiasEnum] = mapped_column(Enum(BiasEnum))
    time_horizon: Mapped[TimeHorizonEnum] = mapped_column(Enum(TimeHorizonEnum))
    confidence_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class SectorMapping(Base):
    __tablename__ = "sector_mappings"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    macro_trigger: Mapped[str] = mapped_column(String) # e.g., "Inflation Up"
    sector: Mapped[str] = mapped_column(String) # e.g., "IT"
    bias: Mapped[BiasEnum] = mapped_column(Enum(BiasEnum))

class IntradaySignal(Base):
    __tablename__ = "intraday_signals"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    sector: Mapped[str] = mapped_column(String, index=True)
    volume_multiplier: Mapped[float] = mapped_column(Float) # e.g., 1.8
    is_below_vwap: Mapped[bool] = mapped_column(Boolean)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    razorpay_sub_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    status: Mapped[str] = mapped_column(String)
    next_billing_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    signal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("classified_signals.id"), nullable=True)
    alert_text: Mapped[str] = mapped_column(String)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)