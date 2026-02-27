import asyncio
import feedparser
import httpx
from datetime import datetime
from email.utils import parsedate_to_datetime

from sqlalchemy.dialects.postgresql import insert
from app.db.database import AsyncSessionLocal
from app.db.models import Event
from app.services.ai import process_new_events

# Spec #2: Locked Data Sources
RSS_FEEDS = {
    # Domestic Feeds (India)
    "RBI Press Releases": "https://www.rbi.org.in/Scripts/rss.aspx",
    "SEBI News": "https://www.sebi.gov.in/sebirss.xml",
    "PIB India (Finance)": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
    "Google News India": "https://news.google.com/rss/search?q=economy+OR+inflation+OR+RBI+OR+GDP+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
    
    # Global Macro Feeds
    "US Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "European Central Bank": "https://www.ecb.europa.eu/rss/press.html",
    "US BLS (CPI & Labor)": "https://www.bls.gov/feed/cpi_latest.rss",
    "Google News Global": "https://news.google.com/rss/search?q=fed+rate+OR+US+CPI+OR+oil+prices+when:1d&hl=en-US&gl=US&ceid=US:en",
}

async def fetch_feed(source_name: str, url: str):
    """Fetches RSS with Browser Headers and Redirect following."""
    # Critical: Headers prevent 403 Forbidden errors from BLS/Fed/RBI
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8"
    }
    
    # follow_redirects=True fixes 301 Moved Permanently for PIB
    async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            return source_name, feed.entries
        except Exception as e:
            print(f"❌ Error fetching {source_name}: {e}")
            return source_name, []

async def process_and_store_entries(source_name: str, entries: list):
    """Parses entries, deduplicates via DB, and fires AI classification."""
    if not entries:
        return 0
        
    new_events = []
    for entry in entries[:10]:
        headline = entry.get("title", "")
        link = entry.get("link", "")
        
        pub_date = datetime.utcnow()
        if "published" in entry:
            try:
                pub_date = parsedate_to_datetime(entry.published).replace(tzinfo=None)
            except Exception:
                pass
        
        new_events.append({
            "source": source_name,
            "headline": headline,
            "summary": entry.get("summary", "")[:500],
            "url": link,
            "published_at": pub_date
        })

    if not new_events:
        return 0

    async with AsyncSessionLocal() as session:
        stmt = insert(Event).values(new_events)
        stmt = stmt.on_conflict_do_nothing(index_elements=['headline'])
        stmt = stmt.returning(Event.id, Event.headline, Event.summary)
        
        result = await session.execute(stmt)
        await session.commit()
        
        inserted_rows = result.mappings().all()
        
        if inserted_rows:
            rows_data = [dict(row) for row in inserted_rows]
            asyncio.create_task(process_new_events(rows_data))
        
        return len(inserted_rows)

async def poll_rss_feeds():
    """Main background job for scheduled ingestion."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    tasks = [fetch_feed(name, url) for name, url in RSS_FEEDS.items()]
    results = await asyncio.gather(*tasks)
    
    total_inserted = 0
    for source_name, entries in results:
        inserted = await process_and_store_entries(source_name, entries)
        total_inserted += inserted
        
    if total_inserted > 0:
        print(f"[{now}] 🚨 NEW MACRO EVENTS DETECTED: {total_inserted} new events inserted.")