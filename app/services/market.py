import asyncio
from typing import Dict, List, Optional
from growwapi import GrowwAPI
from sqlalchemy.dialects.postgresql import insert
from app.db.database import AsyncSessionLocal
from app.db.models import IntradaySignal
from app.core.config import settings

intraday_data: Dict[str, Dict] = {}

# SPEC #5: Exact underlying_symbol and trading_symbol from Groww CSV
SECTOR_CONSTITUENTS = {
    "BANKNIFTY": ["HDFCBANK", "ICICIBANK"],
    "NIFTYIT": ["INFY", "TCS"],
    "NIFTYPHARMA": ["SUNPHARMA", "CIPLA"],
    "NIFTYAUTO": ["TATAMOTORS", "M&M"], # Groww usually maps M&M to M_M
    "NIFTYFMCG": ["ITC", "HINDUNILVR"],
    "NIFTYMETAL": ["TATASTEEL", "JINDALSTEL"],
    "NIFTYREALTY": ["DLF", "LODHA"],
    "NIFTYMEDIA": ["SUNTV", "ZEEL"],
    "NIFTYENERGY": ["RELIANCE", "ONGC"],
    "NIFTYINFRA": ["LT", "RELIANCE"]
}

groww_client: Optional[GrowwAPI] = None

async def init_groww():
    """Initializes the SDK safely inside the FastAPI event loop."""
    global groww_client
    if groww_client is None:
        try:
            token = await asyncio.to_thread(
                GrowwAPI.get_access_token, 
                api_key=settings.GROWW_API_KEY, 
                secret=settings.GROWW_API_SECRET
            )
            groww_client = GrowwAPI(token)
            print("✅ Groww SDK Authenticated successfully.")
        except Exception as e:
            print(f"❌ Groww Auth Failed: {e}")
            return None
    return groww_client

def update_vwap_and_volume(sector: str, price: float, volume: int) -> Dict:
    """Calculates running VWAP and 20-period volume average."""
    if sector not in intraday_data:
        intraday_data[sector] = {"total_volume": 0, "total_pv": 0.0, "history_vol": []}
    
    data = intraday_data[sector]
    data["total_pv"] += (price * volume)
    data["total_volume"] += volume
    vwap = data["total_pv"] / data["total_volume"] if data["total_volume"] > 0 else price
    
    data["history_vol"].append(volume)
    if len(data["history_vol"]) > 20: 
        data["history_vol"].pop(0)
        
    avg_vol = sum(data["history_vol"]) / len(data["history_vol"])
    vol_multiplier = volume / avg_vol if avg_vol > 0 else 1.0
    
    return {"vwap": vwap, "is_below_vwap": price < vwap, "vol_multiplier": vol_multiplier}

async def check_intraday_confirmation():
    """Polls exact CSV symbols to trigger Intraday Alerts."""
    client = await init_groww()
    if not client: return

    # Prepare symbols with the required 'NSE_' prefix for get_ltp
    unique_symbols = set()
    for sector, stocks in SECTOR_CONSTITUENTS.items():
        unique_symbols.add(f"NSE_{sector}")
        for stock in stocks:
            unique_symbols.add(f"NSE_{stock}")

    # SDK requires a tuple of strings
    symbols_tuple = tuple(unique_symbols)

    try:
        # Use get_ltp to fetch the data
        ltp_response = await asyncio.to_thread(
            client.get_ltp,
            exchange_trading_symbols=symbols_tuple,
            segment=client.SEGMENT_CASH
        )
        
        quotes = {}
        
        # --- THE FIX: Defensively parse the response based on its data type ---
        
        # Case 1: The SDK returns a dictionary (e.g., {'NSE_INFY': {'last_price': 1500}})
        if isinstance(ltp_response, dict):
            # Check if it returned an API error inside the dict
            if ltp_response.get("status") == "error" or "error" in ltp_response:
                print(f"❌ Groww API returned an error: {ltp_response}")
                return
                
            for key, value in ltp_response.items():
                clean_key = key.replace('NSE_', '')
                if isinstance(value, dict):
                    quotes[clean_key] = value
                elif isinstance(value, (float, int)): # Sometimes it just returns the raw number
                    quotes[clean_key] = {'last_price': float(value)}
                    
        # Case 2: The SDK returns a list of dicts (e.g., [{'trading_symbol': 'NSE_INFY'}])
        elif isinstance(ltp_response, list):
            for item in ltp_response:
                if isinstance(item, dict):
                    # Try to find the symbol key, fallback to empty string
                    sym = item.get('trading_symbol', item.get('symbol', '')).replace('NSE_', '')
                    quotes[sym] = item
        else:
            print(f"❌ Unexpected response format from Groww: {type(ltp_response)}")
            return

    except Exception as e:
        print(f"❌ Groww Data Fetch Error: {e}")
        return

    signals_to_save = []
    for sector, stocks in SECTOR_CONSTITUENTS.items():
        s_data = quotes.get(sector)
        if not s_data: continue

        # Handle price key safely (could be 'last_price' or 'ltp' depending on SDK version)
        s_price = s_data.get('last_price', s_data.get('ltp', 0.0))
        if s_price == 0.0: continue

        calc = update_vwap_and_volume(sector, s_price, 1000) 
        
        # Verify 2 Heavyweight Stocks Align with Sector
        alignment = 0
        for stock in stocks:
            stk_data = quotes.get(stock)
            if stk_data:
                stk_price = stk_data.get('last_price', stk_data.get('ltp', 0.0))
                if (stk_price < s_price) == calc["is_below_vwap"]:
                    alignment += 1
        
        if calc["vol_multiplier"] >= 1.5 and alignment >= 2:
            signals_to_save.append({
                "sector": sector,
                "volume_multiplier": calc["vol_multiplier"],
                "is_below_vwap": calc["is_below_vwap"],
                "is_active": True
            })

    if signals_to_save:
        async with AsyncSessionLocal() as session:
            await session.execute(insert(IntradaySignal).values(signals_to_save))
            await session.commit()
            print(f"✅ Saved {len(signals_to_save)} confirmed intraday signals.")