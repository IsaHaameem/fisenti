import json
from pydantic import BaseModel, Field
from typing import List, Optional
from openai import AsyncOpenAI

from sqlalchemy.dialects.postgresql import insert
from app.db.database import AsyncSessionLocal
from app.db.models import ClassifiedSignal
from app.core.config import settings

# Initialize OpenAI Async Client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# 1. The Rule-Based Filter
MACRO_KEYWORDS = [
    "cpi", "inflation", "rate", "gdp", "tariff", "sanction", 
    "oil", "war", "fed", "rbi", "sebi", "employment", "payroll"
]

def passes_macro_filter(text: str) -> bool:
    """Returns True if the text contains any of our critical macro keywords."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in MACRO_KEYWORDS)

# 2. Pydantic Schema for Strict AI Output
class SignalOutput(BaseModel):
    event_type: str = Field(description="e.g., 'Rate Hike', 'Inflation Data', 'Geopolitical'")
    severity: str = Field(description="Must be exactly: 'High', 'Medium', or 'Low'")
    region: str = Field(description="e.g., 'US', 'India', 'Global'")
    affected_sectors: List[str] = Field(description="List of impacted sectors, e.g. ['IT', 'Banking']")
    bias_direction: str = Field(description="Must be exactly: 'Bullish', 'Bearish', or 'Neutral'")
    time_horizon: str = Field(description="Must be exactly: 'Intraday' or 'Swing'")
    confidence_score: float = Field(description="Float between 0.0 and 1.0")

# 3. The OpenAI Classification Engine
async def classify_event_with_ai(headline: str, summary: str) -> Optional[SignalOutput]:
    """Sends the event to gpt-4o-mini and returns validated structured data."""
    prompt = f"""
    You are a senior macro-economic quantitative analyst.
    Analyze the following news event and determine its market impact on the Indian stock market (NIFTY 50 / Sectors).
    
    Headline: {headline}
    Summary: {summary}
    """

    try:
        # We use parse() to force the model to return our exact Pydantic schema
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a financial AI. Output strictly valid JSON matching the schema."},
                {"role": "user", "content": prompt}
            ],
            response_format=SignalOutput,
            temperature=0.1 # Keep it deterministic and analytical
        )
        
        return response.choices[0].message.parsed
        
    except Exception as e:
        print(f"❌ OpenAI API Error: {e}")
        return None

# 4. Orchestrator: Filter -> Classify -> Save
async def process_new_events(new_events_data: list):
    """Takes freshly inserted events, filters them, classifies them, and saves signals."""
    if not new_events_data:
        return

    signals_to_insert = []
    
    for event in new_events_data:
        event_id, headline, summary = event['id'], event['headline'], event['summary']
        
        # Step A: Rule-Based Filter
        combined_text = f"{headline} {summary}"
        if not passes_macro_filter(combined_text):
            continue # Skip irrelevant news
            
        print(f"🧠 AI Analyzing: {headline[:50]}...")
        
        # Step B: AI Classification
        ai_result = await classify_event_with_ai(headline, summary)
        if not ai_result:
            continue
            
        # Step C: Prepare for Database Insertion
        signals_to_insert.append({
            "event_id": event_id,
            "event_type": ai_result.event_type,
            "severity": ai_result.severity,
            "region": ai_result.region,
            "affected_sectors": ai_result.affected_sectors,
            "bias_direction": ai_result.bias_direction,
            "time_horizon": ai_result.time_horizon,
            "confidence_score": ai_result.confidence_score
        })

    # Step D: Bulk Insert Signals into DB
    if signals_to_insert:
        async with AsyncSessionLocal() as session:
            stmt = insert(ClassifiedSignal).values(signals_to_insert)
            await session.execute(stmt)
            await session.commit()
            print(f"✅ Saved {len(signals_to_insert)} new AI signals to database.")