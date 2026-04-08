"""
Cross-Platform Arbitrage Engine — FIXED
Uses updated polymarket.py and kalshi.py service functions.
"""

import asyncio
import logging
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone

from services.polymarket import get_active_markets as poly_markets
from services.kalshi     import get_active_markets as kalshi_markets

logger = logging.getLogger(__name__)

TOPIC_KEYWORDS = [
    ["bitcoin", "btc"],
    ["ethereum", "eth"],
    ["fed", "federal reserve", "interest rate", "fomc"],
    ["trump", "donald trump"],
    ["biden", "joe biden"],
    ["election", "vote", "ballot"],
    ["inflation", "cpi"],
    ["recession"],
    ["rate cut", "rate hike"],
    ["gdp"],
    ["nba", "basketball"],
    ["nfl", "football", "super bowl"],
    ["world cup", "soccer"],
    ["ukraine", "russia"],
    ["china", "taiwan"],
    ["oil", "crude", "opec"],
    ["gold"],
    ["nasdaq", "s&p", "dow"],
    ["climate", "temperature", "weather"],
    ["oscar", "emmy", "grammy"],
    ["spacex", "nasa", "rocket"],
]


def _topic_key(question: str) -> Optional[str]:
    q = question.lower()
    for group in TOPIC_KEYWORDS:
        if any(kw in q for kw in group):
            return group[0]
    return None


def _match_markets(poly: List[Dict], kalshi: List[Dict]) -> List[Tuple[Dict, Dict]]:
    pairs = []
    kalshi_by_topic: Dict[str, List[Dict]] = {}
    for km in kalshi:
        key = _topic_key(km["question"])
        if key:
            kalshi_by_topic.setdefault(key, []).append(km)

    seen_kal = set()
    for pm in poly:
        key = _topic_key(pm["question"])
        if not key or key not in kalshi_by_topic:
            continue
        # Pick highest-volume Kalshi market in same topic
        candidates = [k for k in kalshi_by_topic[key] if k["id"] not in seen_kal]
        if not candidates:
            continue
        best = max(candidates, key=lambda x: x.get("volume", 0))
        seen_kal.add(best["id"])
        pairs.append((pm, best))

    return pairs


# ── Arb finders ───────────────────────────────────────────────────────────────

def find_cross_platform_arb(pairs: List[Tuple[Dict, Dict]]) -> List[Dict]:
    """
    Best case: buy YES on one platform + NO on the other for < $1.
    Guaranteed $1 at resolution. Net profit = 1 - total_cost.
    """
    opps = []
    for pm, km in pairs:
        # Side 1: YES on Poly, NO on Kalshi
        cost1   = pm["yes"] + km["no"]
        profit1 = 1.0 - cost1

        # Side 2: YES on Kalshi, NO on Poly
        cost2   = km["yes"] + pm["no"]
        profit2 = 1.0 - cost2

        best_profit = max(profit1, profit2)
        if best_profit < 0.015:
            continue

        if profit1 >= profit2:
            action     = f"BUY YES on Polymarket ({int(pm['yes']*100)}c) + BUY NO on Kalshi ({int(km['no']*100)}c)"
            poly_side  = "YES";  kal_side  = "NO"
            poly_price = pm["yes"]; kal_price = km["no"]
        else:
            action     = f"BUY YES on Kalshi ({int(km['yes']*100)}c) + BUY NO on Polymarket ({int(pm['no']*100)}c)"
            poly_side  = "NO";   kal_side  = "YES"
            poly_price = pm["no"]; kal_price = km["yes"]

        opps.append({
            "arb_type":       "Cross-Platform",
            "event_topic":    _topic_key(pm["question"]) or "?",
            "poly_question":  pm["question"],
            "kal_question":   km["question"],
            "poly_yes":       pm["yes"],
            "poly_no":        pm["no"],
            "kal_yes":        km["yes"],
            "kal_no":         km["no"],
            "poly_side":      poly_side,
            "kal_side":       kal_side,
            "poly_price":     poly_price,
            "kal_price":      kal_price,
            "total_cost":     round(1 - best_profit, 4),
            "profit_pct":     round(best_profit * 100, 2),
            "action":         action,
            "poly_url":       pm.get("url", ""),
            "kal_url":        km.get("url", ""),
            "poly_liquidity": pm.get("liquidity", 0),
            "kal_liquidity":  km.get("liquidity", 0),
            "confidence":     min(97, int(55 + best_profit * 300)),
            "score":          min(99, int(50 + best_profit * 250)),
        })

    opps.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opps[:8]


def find_sum_deviation_arb(poly: List[Dict], kalshi: List[Dict]) -> List[Dict]:
    """YES + NO != 1.0 on a single platform = guaranteed profit."""
    opps = []

    def check(markets: List[Dict], platform: str):
        for m in markets:
            yes = m.get("yes", 0)
            no  = m.get("no",  0)
            if yes <= 0 or no <= 0:
                continue
            total = yes + no
            dev   = total - 1.0
            profit_pct = abs(dev) * 100
            if profit_pct < 1.5:
                continue
            opps.append({
                "arb_type":   "Sum Deviation",
                "platform":   platform,
                "question":   m.get("question", "?"),
                "yes":        yes,
                "no":         no,
                "sum":        round(total, 4),
                "profit_pct": round(profit_pct, 2),
                "action":     "BUY YES + BUY NO" if dev < 0 else "SELL YES + SELL NO",
                "url":        m.get("url", ""),
                "liquidity":  m.get("liquidity", 0),
                "confidence": min(95, int(45 + profit_pct * 12)),
                "score":      min(99, int(45 + profit_pct * 12)),
            })

    check(poly,   "Polymarket")
    check(kalshi, "Kalshi")
    opps.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opps[:8]


def find_spread_opportunities(kalshi: List[Dict]) -> List[Dict]:
    """Wide Kalshi bid/ask spreads = market-making opportunity."""
    opps = []
    for m in kalshi:
        spread = m.get("spread")
        if spread is None or spread < 0.03:
            continue
        mid = (m["yes_bid"] + m["yes_ask"]) / 2
        opps.append({
            "arb_type": "Spread / Market Making",
            "platform": "Kalshi",
            "question": m["question"],
            "yes_bid":  m["yes_bid"],
            "yes_ask":  m["yes_ask"],
            "spread":   round(spread * 100, 1),
            "mid":      round(mid * 100, 1),
            "action":   f"Post YES bid at {int(m['yes_bid']*100+1)}c, YES ask at {int(m['yes_ask']*100-1)}c",
            "url":      m.get("url", ""),
            "volume":   m.get("volume", 0),
            "score":    min(99, int(40 + spread * 400)),
            "confidence": min(90, int(40 + spread * 300)),
        })
    opps.sort(key=lambda x: x["spread"], reverse=True)
    return opps[:6]


# ── Master runner ─────────────────────────────────────────────────────────────

async def find_all_arb() -> Dict:
    poly_data, kal_data = await asyncio.gather(
        poly_markets(300),
        kalshi_markets(200),
        return_exceptions=True
    )

    poly   = poly_data  if not isinstance(poly_data,  Exception) else []
    kalshi = kal_data   if not isinstance(kal_data,   Exception) else []

    if isinstance(poly_data, Exception):
        logger.error(f"Polymarket fetch error: {poly_data}")
    if isinstance(kal_data, Exception):
        logger.error(f"Kalshi fetch error: {kal_data}")

    pairs          = _match_markets(poly, kalshi)
    cross_platform = find_cross_platform_arb(pairs)
    sum_dev        = find_sum_deviation_arb(poly, kalshi)
    spreads        = find_spread_opportunities(kalshi)

    return {
        "cross_platform":      cross_platform,
        "sum_deviation":       sum_dev,
        "spread_making":       spreads,
        "matched_pairs":       len(pairs),
        "poly_markets":        len(poly),
        "kalshi_markets":      len(kalshi),
        "total_opportunities": len(cross_platform) + len(sum_dev) + len(spreads),
        "timestamp":           datetime.now(timezone.utc).isoformat(),
        "errors": {
            "poly":   str(poly_data)   if isinstance(poly_data,  Exception) else None,
            "kalshi": str(kal_data)    if isinstance(kal_data,   Exception) else None,
        }
    }
