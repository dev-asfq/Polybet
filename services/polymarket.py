"""
Polymarket Service
- Gamma API: market metadata, prices, volumes, categories
- CLOB API: live orderbook, best bid/ask spreads
- Detects: mispriced markets, sharp money moves, volume spikes
"""

import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"

# Categories we care about for trading signals
TRADEABLE_CATEGORIES = {"Politics", "Crypto", "Sports", "Economics", "Science", "World"}


async def _get(session: aiohttp.ClientSession, url: str, params: dict = None) -> Optional[any]:
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.warning(f"GET {url} failed: {e}")
    return None


# ── Market fetching ──────────────────────────────────────────────────────────

async def get_active_markets(limit: int = 200) -> List[Dict]:
    """Fetch active, liquid Polymarket markets."""
    async with aiohttp.ClientSession() as s:
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": "volume24hr",
            "ascending": "false",
        }
        data = await _get(s, f"{GAMMA_BASE}/markets", params)
        if not data:
            return []
        markets = data if isinstance(data, list) else data.get("markets", [])
        out = []
        for m in markets:
            prices = m.get("outcomePrices") or []
            if not prices:
                continue
            try:
                yes = float(prices[0])
                no  = float(prices[1]) if len(prices) > 1 else round(1 - yes, 4)
            except Exception:
                continue

            liq = float(m.get("liquidity") or 0)
            vol = float(m.get("volume") or 0)
            vol24 = float(m.get("volume24hr") or 0)

            if liq < 500:          # Skip dust markets
                continue

            out.append({
                "id":          m.get("id", ""),
                "condition_id": m.get("conditionId", ""),
                "question":    m.get("question", ""),
                "category":    m.get("category", ""),
                "yes":         yes,
                "no":          no,
                "sum":         round(yes + no, 4),
                "liquidity":   liq,
                "volume":      vol,
                "volume_24h":  vol24,
                "end_date":    m.get("endDate", ""),
                "slug":        m.get("slug", ""),
                "url":         f"https://polymarket.com/event/{m.get('slug', '')}",
            })
        return out


async def get_clob_orderbook(token_id: str) -> Optional[Dict]:
    """Fetch live orderbook for a specific token."""
    async with aiohttp.ClientSession() as s:
        data = await _get(s, f"{CLOB_BASE}/book", {"token_id": token_id})
        return data


async def get_market_trades(condition_id: str, limit: int = 50) -> List[Dict]:
    """Fetch recent trades for a market."""
    async with aiohttp.ClientSession() as s:
        params = {"market": condition_id, "limit": limit}
        data = await _get(s, f"{CLOB_BASE}/trades", params)
        if not data:
            return []
        return data if isinstance(data, list) else data.get("trades", [])


# ── Signal detection ─────────────────────────────────────────────────────────

def find_mispriced_markets(markets: List[Dict]) -> List[Dict]:
    """
    Markets where YES + NO ≠ 1.0 by more than 1.5%.
    The gap = free money if you can trade both sides before it closes.
    """
    opps = []
    for m in markets:
        dev = m["sum"] - 1.0
        if abs(dev) < 0.015:
            continue
        profit_pct = abs(dev) * 100
        opps.append({
            **m,
            "arb_type":    "Sum Deviation",
            "deviation":   dev,
            "profit_pct":  profit_pct,
            "action":      "BUY YES + BUY NO" if dev < 0 else "SELL YES + SELL NO",
            "score":       min(99, int(40 + profit_pct * 15)),
        })
    opps.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opps[:10]


def find_volume_spike_markets(markets: List[Dict]) -> List[Dict]:
    """
    Markets where 24h volume is a large fraction of total volume
    — implies sudden sharp-money interest.
    """
    spikes = []
    for m in markets:
        if m["volume"] < 5000 or m["volume_24h"] < 1000:
            continue
        ratio = m["volume_24h"] / max(m["volume"], 1)
        if ratio < 0.15:   # at least 15% of all-time vol happened today
            continue
        score = min(99, int(50 + ratio * 120))
        spikes.append({
            **m,
            "spike_ratio": ratio,
            "spike_pct":   round(ratio * 100, 1),
            "score":       score,
        })
    spikes.sort(key=lambda x: x["spike_ratio"], reverse=True)
    return spikes[:10]


def find_edge_markets(markets: List[Dict]) -> List[Dict]:
    """
    Markets where YES is priced between 5¢–20¢ or 80¢–95¢
    (near-binary outcomes) with decent liquidity — highest EV bets.
    """
    edges = []
    for m in markets:
        yes = m["yes"]
        liq = m["liquidity"]
        if liq < 2000:
            continue

        if 0.05 <= yes <= 0.20:
            # Cheap YES — small probability, huge upside
            implied_odds = round(1 / yes, 1)
            score = min(99, int(55 + (0.20 - yes) * 200))
            edges.append({
                **m,
                "edge_type":    "Long Shot YES",
                "implied_odds": f"{implied_odds}x",
                "ev_note":      f"Pays {implied_odds}x if YES. Market says {int(yes*100)}% chance.",
                "score":        score,
            })
        elif 0.80 <= yes <= 0.95:
            # Near-certainty YES — low risk, lock-in
            no_odds = round(1 / m["no"], 1)
            score = min(99, int(60 + (yes - 0.80) * 200))
            edges.append({
                **m,
                "edge_type":    "Near-Certain YES",
                "implied_odds": f"{no_odds}x on NO",
                "ev_note":      f"YES at {int(yes*100)}¢ — only {int(m['no']*100)}% downside.",
                "score":        score,
            })

    edges.sort(key=lambda x: x["score"], reverse=True)
    return edges[:10]


def find_high_value_bets(markets: List[Dict]) -> List[Dict]:
    """
    General best-bet scanner: liquid markets, high volume, prices 20–80¢
    (genuine uncertainty = trading opportunity).
    """
    bets = []
    for m in markets:
        yes = m["yes"]
        if not (0.20 < yes < 0.80):
            continue
        if m["liquidity"] < 3000 or m["volume_24h"] < 500:
            continue

        # Score based on liquidity depth and activity
        liq_score  = min(30, int(m["liquidity"] / 1000))
        vol_score  = min(30, int(m["volume_24h"] / 500))
        price_score = int(20 - abs(yes - 0.5) * 40)  # peak at 0.5
        score = 30 + liq_score + vol_score + price_score

        bets.append({
            **m,
            "bet_type": "Active Market",
            "score":    min(99, score),
        })

    bets.sort(key=lambda x: x["score"], reverse=True)
    return bets[:12]


async def get_all_signals() -> Dict:
    """Master function — runs all signal detectors in parallel."""
    markets = await get_active_markets(300)
    if not markets:
        return {"error": "Could not fetch Polymarket data", "markets": []}

    mispriced   = find_mispriced_markets(markets)
    vol_spikes  = find_volume_spike_markets(markets)
    edge_bets   = find_edge_markets(markets)
    best_bets   = find_high_value_bets(markets)

    return {
        "mispriced":   mispriced,
        "vol_spikes":  vol_spikes,
        "edge_bets":   edge_bets,
        "best_bets":   best_bets,
        "total_scanned": len(markets),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
