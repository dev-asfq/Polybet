"""
Polymarket Service — FIXED
- Gamma API: correct headers, outcomePrices is a JSON string OR list
- CLOB API: correct endpoints for trades and orderbook
- Robust parsing with multiple fallbacks
"""

import aiohttp
import asyncio
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"

# Polymarket blocks requests without a browser-like User-Agent
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PMBot/1.0)",
    "Accept": "application/json",
    "Origin": "https://polymarket.com",
    "Referer": "https://polymarket.com/",
}


async def _get(session: aiohttp.ClientSession, url: str,
               params: dict = None, headers: dict = None) -> Optional[any]:
    h = {**HEADERS, **(headers or {})}
    try:
        async with session.get(
            url, params=params, headers=h,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            if r.status == 200:
                text = await r.text()
                if not text.strip():
                    return None
                return json.loads(text)
            else:
                body = await r.text()
                logger.warning(f"GET {url} -> {r.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"GET {url} failed: {e}")
    return None


def _parse_outcome_prices(raw) -> Optional[tuple]:
    """
    outcomePrices can be:
      - a list:   [0.72, 0.28]
      - a JSON string: "[\"0.72\", \"0.28\"]"
      - None / missing
    Returns (yes, no) floats or None.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        prices = raw
    elif isinstance(raw, str):
        try:
            prices = json.loads(raw)
        except Exception:
            return None
    else:
        return None

    if len(prices) < 2:
        return None
    try:
        return float(prices[0]), float(prices[1])
    except Exception:
        return None


# ── Market fetching ────────────────────────────────────────────────────────

async def get_active_markets(limit: int = 200) -> List[Dict]:
    """Fetch active liquid Polymarket markets via Gamma API."""
    async with aiohttp.ClientSession() as s:
        all_markets = []
        offset = 0
        page_size = min(limit, 100)

        while len(all_markets) < limit:
            params = {
                "active":    "true",
                "closed":    "false",
                "limit":     page_size,
                "offset":    offset,
                "order":     "volume24hr",
                "ascending": "false",
            }
            data = await _get(s, f"{GAMMA_BASE}/markets", params)
            if not data:
                break

            page = data if isinstance(data, list) else data.get("markets", [])
            if not page:
                break

            all_markets.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        out = []
        for m in all_markets:
            parsed = _parse_outcome_prices(m.get("outcomePrices"))
            if parsed is None:
                continue
            yes, no = parsed

            liq   = float(m.get("liquidity")  or m.get("liquidityNum")  or 0)
            vol   = float(m.get("volume")     or m.get("volumeNum")     or 0)
            vol24 = float(m.get("volume24hr") or 0)

            if liq < 500:
                continue

            slug = m.get("slug") or m.get("marketSlug") or ""
            url  = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"

            out.append({
                "id":           m.get("id", ""),
                "condition_id": m.get("conditionId", ""),
                "question":     m.get("question", ""),
                "category":     m.get("category", ""),
                "yes":          round(yes, 4),
                "no":           round(no,  4),
                "sum":          round(yes + no, 4),
                "liquidity":    liq,
                "volume":       vol,
                "volume_24h":   vol24,
                "end_date":     m.get("endDate") or m.get("endDateIso", ""),
                "slug":         slug,
                "url":          url,
                "enable_order_book": m.get("enableOrderBook", False),
            })

        logger.info(f"Polymarket: fetched {len(out)} markets")
        return out


async def get_recent_trades_clob(limit: int = 100) -> List[Dict]:
    """Fetch recent trades from CLOB API."""
    async with aiohttp.ClientSession() as s:
        params = {"limit": limit}
        data = await _get(s, f"{CLOB_BASE}/trades", params)
        if not data:
            return []

        trades = data if isinstance(data, list) else data.get("trades", [])
        out = []
        for t in trades:
            try:
                size  = float(t.get("size", 0) or 0)
                price = float(t.get("price", 0) or 0)
                value = size * price
                out.append({
                    "market_id": t.get("market", t.get("conditionId", "")),
                    "side":      t.get("side", "BUY"),
                    "price":     round(price, 4),
                    "size":      round(size, 2),
                    "value_usd": round(value, 2),
                    "timestamp": t.get("timestamp", t.get("createdAt", "")),
                    "maker":     t.get("maker_address", t.get("maker", "")),
                    "taker":     t.get("taker_address", t.get("taker", "")),
                })
            except Exception:
                continue
        return out


# ── Signal detectors ────────────────────────────────────────────────────────

def find_mispriced_markets(markets: List[Dict]) -> List[Dict]:
    opps = []
    for m in markets:
        dev = m["sum"] - 1.0
        if abs(dev) < 0.015:
            continue
        profit_pct = abs(dev) * 100
        opps.append({
            **m,
            "arb_type":   "Sum Deviation",
            "deviation":  dev,
            "profit_pct": profit_pct,
            "action":     "BUY YES + BUY NO" if dev < 0 else "SELL YES + SELL NO",
            "score":      min(99, int(40 + profit_pct * 15)),
        })
    opps.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opps[:10]


def find_volume_spike_markets(markets: List[Dict]) -> List[Dict]:
    spikes = []
    for m in markets:
        if m["volume"] < 5000 or m["volume_24h"] < 1000:
            continue
        ratio = m["volume_24h"] / max(m["volume"], 1)
        if ratio < 0.15:
            continue
        score = min(99, int(50 + ratio * 120))
        spikes.append({**m, "spike_ratio": ratio,
                       "spike_pct": round(ratio * 100, 1), "score": score})
    spikes.sort(key=lambda x: x["spike_ratio"], reverse=True)
    return spikes[:10]


def find_edge_markets(markets: List[Dict]) -> List[Dict]:
    edges = []
    for m in markets:
        yes = m["yes"]
        if m["liquidity"] < 2000:
            continue
        if 0.05 <= yes <= 0.20:
            implied_odds = round(1 / yes, 1)
            edges.append({
                **m,
                "edge_type":    "Long Shot YES",
                "implied_odds": f"{implied_odds}x",
                "ev_note":      f"Pays {implied_odds}x if YES. Market says {int(yes*100)}% chance.",
                "score":        min(99, int(55 + (0.20 - yes) * 200)),
            })
        elif 0.80 <= yes <= 0.95:
            no_odds = round(1 / m["no"], 1)
            edges.append({
                **m,
                "edge_type":    "Near-Certain YES",
                "implied_odds": f"{no_odds}x on NO",
                "ev_note":      f"YES at {int(yes*100)}c - only {int(m['no']*100)}% downside.",
                "score":        min(99, int(60 + (yes - 0.80) * 200)),
            })
    edges.sort(key=lambda x: x["score"], reverse=True)
    return edges[:10]


def find_high_value_bets(markets: List[Dict]) -> List[Dict]:
    bets = []
    for m in markets:
        yes = m["yes"]
        if not (0.20 < yes < 0.80):
            continue
        if m["liquidity"] < 3000 or m["volume_24h"] < 500:
            continue
        liq_score   = min(30, int(m["liquidity"] / 1000))
        vol_score   = min(30, int(m["volume_24h"] / 500))
        price_score = int(20 - abs(yes - 0.5) * 40)
        score = min(99, 30 + liq_score + vol_score + price_score)
        bets.append({**m, "bet_type": "Active Market", "score": score})
    bets.sort(key=lambda x: x["score"], reverse=True)
    return bets[:12]


async def get_all_signals() -> Dict:
    markets = await get_active_markets(300)
    if not markets:
        return {
            "error": "Could not fetch Polymarket data. API may be rate-limiting — try again in 30s.",
            "markets": []
        }
    return {
        "mispriced":     find_mispriced_markets(markets),
        "vol_spikes":    find_volume_spike_markets(markets),
        "edge_bets":     find_edge_markets(markets),
        "best_bets":     find_high_value_bets(markets),
        "total_scanned": len(markets),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }
