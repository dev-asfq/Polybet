"""
Kalshi Service — FIXED
Correct base URL: https://api.elections.kalshi.com/trade-api/v2
(Despite "elections" subdomain, this serves ALL Kalshi markets)
Prices are in CENTS (0-100), not 0-1 fractions.
Public endpoints require no API key.
"""

import aiohttp
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Correct production URL (confirmed from official Kalshi docs 2025)
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PMBot/1.0)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


async def _get(session: aiohttp.ClientSession, path: str,
               params: dict = None) -> Optional[any]:
    url = f"{KALSHI_BASE}{path}"
    try:
        async with session.get(
            url, params=params, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status == 200:
                text = await r.text()
                if not text.strip():
                    return None
                return json.loads(text)
            else:
                body = await r.text()
                logger.warning(f"Kalshi {url} -> {r.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"Kalshi GET {url} failed: {e}")
    return None


async def get_active_markets(limit: int = 200) -> List[Dict]:
    """
    Fetch Kalshi active markets. Prices in cents (0-100), convert to 0-1.
    Uses cursor-based pagination.
    """
    async with aiohttp.ClientSession() as s:
        all_markets = []
        cursor = None

        while len(all_markets) < limit:
            params = {"status": "open", "limit": min(100, limit)}
            if cursor:
                params["cursor"] = cursor

            data = await _get(s, "/markets", params)
            if not data:
                break

            raw = data.get("markets", [])
            if not raw:
                break

            for m in raw:
                # Kalshi prices: yes_bid, yes_ask, no_bid, no_ask all in cents (0-100)
                yes_bid_c = m.get("yes_bid", 0) or 0
                yes_ask_c = m.get("yes_ask", 0) or 0
                no_bid_c  = m.get("no_bid",  0) or 0
                no_ask_c  = m.get("no_ask",  0) or 0

                # Skip markets with no quotes
                if yes_ask_c == 0 and yes_bid_c == 0:
                    continue

                # Convert to 0-1 fractions
                yes_bid = yes_bid_c / 100
                yes_ask = yes_ask_c / 100
                no_bid  = no_bid_c  / 100
                no_ask  = no_ask_c  / 100

                yes_mid = (yes_bid + yes_ask) / 2 if yes_ask_c > 0 else yes_bid
                no_mid  = (no_bid  + no_ask)  / 2 if no_ask_c  > 0 else no_bid

                # Fallback: if no_mid missing, derive from yes
                if no_mid == 0 and yes_mid > 0:
                    no_mid = round(1 - yes_mid, 4)

                spread = round(yes_ask - yes_bid, 4) if yes_ask_c > 0 else None

                # Volume — Kalshi uses 'volume' (integer contracts) or 'dollar_volume'
                volume  = int(m.get("volume", 0)        or 0)
                open_int = int(m.get("open_interest", 0) or 0)

                ticker = m.get("ticker", "")
                all_markets.append({
                    "id":          ticker,
                    "question":    m.get("title", ""),
                    "category":    m.get("category", ""),
                    "yes":         round(yes_mid, 4),
                    "no":          round(no_mid,  4),
                    "yes_bid":     yes_bid,
                    "yes_ask":     yes_ask,
                    "no_bid":      no_bid,
                    "no_ask":      no_ask,
                    "spread":      spread,
                    "volume":      volume,
                    "liquidity":   open_int,
                    "end_date":    m.get("close_time", ""),
                    "platform":    "Kalshi",
                    "url":         f"https://kalshi.com/markets/{ticker}",
                    "event_ticker": m.get("event_ticker", ""),
                    "status":      m.get("status", "open"),
                })

            # Pagination
            cursor = data.get("cursor")
            if not cursor or len(all_markets) >= limit:
                break

        logger.info(f"Kalshi: fetched {len(all_markets)} markets")
        return all_markets[:limit]


async def get_market_orderbook(ticker: str) -> Optional[Dict]:
    """Fetch orderbook for a specific Kalshi market."""
    async with aiohttp.ClientSession() as s:
        data = await _get(s, f"/markets/{ticker}/orderbook")
        return data


async def get_events(limit: int = 50) -> List[Dict]:
    """Fetch Kalshi events (groups of related markets)."""
    async with aiohttp.ClientSession() as s:
        params = {"status": "open", "limit": limit}
        data = await _get(s, "/events", params)
        if not data:
            return []
        return data.get("events", [])
