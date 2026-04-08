"""
Kalshi Service
- REST API v2 (public endpoints, no auth needed for market data)
- Fetches active markets, prices, volume
- Normalises to same schema as Polymarket for cross-platform arb
"""

import aiohttp
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"


async def _get(session: aiohttp.ClientSession, path: str, params: dict = None) -> Optional[any]:
    url = f"{KALSHI_BASE}{path}"
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
            logger.warning(f"Kalshi {url} → {r.status}")
    except Exception as e:
        logger.warning(f"Kalshi GET {url} failed: {e}")
    return None


async def get_active_markets(limit: int = 200) -> List[Dict]:
    """Fetch Kalshi active markets and normalise prices."""
    async with aiohttp.ClientSession() as s:
        params = {"status": "open", "limit": limit}
        data = await _get(s, "/markets", params)
        if not data:
            return []

        raw = data.get("markets", [])
        out = []
        for m in raw:
            yes_bid  = m.get("yes_bid",  0) or 0
            yes_ask  = m.get("yes_ask",  0) or 0
            no_bid   = m.get("no_bid",   0) or 0
            no_ask   = m.get("no_ask",   0) or 0

            # Kalshi prices are in cents (0-100), convert to 0-1
            yes_mid  = ((yes_bid + yes_ask) / 2) / 100 if yes_ask else None
            no_mid   = ((no_bid  + no_ask)  / 2) / 100 if no_ask  else None
            if yes_mid is None:
                continue

            vol = int(m.get("volume", 0) or 0)
            liq = int(m.get("open_interest", 0) or 0)

            out.append({
                "id":          m.get("ticker", ""),
                "question":    m.get("title", ""),
                "category":    m.get("category", ""),
                "yes":         round(yes_mid, 4),
                "no":          round(no_mid or (1 - yes_mid), 4),
                "yes_bid":     yes_bid / 100,
                "yes_ask":     yes_ask / 100,
                "no_bid":      no_bid  / 100,
                "no_ask":      no_ask  / 100,
                "spread":      round((yes_ask - yes_bid) / 100, 4) if yes_ask else None,
                "volume":      vol,
                "liquidity":   liq,
                "end_date":    m.get("close_time", ""),
                "platform":    "Kalshi",
                "url":         f"https://kalshi.com/markets/{m.get('ticker', '')}",
            })
        return out


async def get_event_markets(event_ticker: str) -> List[Dict]:
    """Get all markets for a specific Kalshi event."""
    async with aiohttp.ClientSession() as s:
        data = await _get(s, f"/events/{event_ticker}/markets")
        if not data:
            return []
        return data.get("markets", [])
