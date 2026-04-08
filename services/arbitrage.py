"""
Cross-Platform Arbitrage Engine
Finds pricing discrepancies between Polymarket and Kalshi
on the same real-world events.

Arb types:
  1. Direct Cross-Platform  — same event, YES cheaper on one platform
  2. Sum Deviation          — YES + NO ≠ 1.0 on a single platform
  3. Correlated Market Arb  — logically linked events priced inconsistently
  4. Spread Scalping        — wide bid/ask spread = market-making opportunity
"""

import asyncio
import logging
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone

from services.polymarket import get_active_markets as poly_markets
from services.kalshi import get_active_markets as kalshi_markets

logger = logging.getLogger(__name__)

# Keywords that help us match the same event across platforms
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
    ["world cup", "soccer", "football"],
    ["ukraine", "russia"],
    ["china", "taiwan"],
    ["oil", "crude", "opec"],
    ["gold"],
    ["nasdaq", "s&p", "dow"],
]


def _topic_key(question: str) -> Optional[str]:
    """Return the first matching topic keyword group for a question."""
    q = question.lower()
    for group in TOPIC_KEYWORDS:
        if any(kw in q for kw in group):
            return group[0]
    return None


def _match_markets(poly: List[Dict], kalshi: List[Dict]) -> List[Tuple[Dict, Dict]]:
    """
    Attempt fuzzy matching between Polymarket and Kalshi markets
    on the same real-world event using topic keywords.
    Returns list of (poly_market, kalshi_market) pairs.
    """
    pairs = []
    kalshi_by_topic: Dict[str, List[Dict]] = {}
    for km in kalshi:
        key = _topic_key(km["question"])
        if key:
            kalshi_by_topic.setdefault(key, []).append(km)

    for pm in poly:
        key = _topic_key(pm["question"])
        if not key or key not in kalshi_by_topic:
            continue
        # Pick the Kalshi market with most volume in same topic
        best = max(kalshi_by_topic[key], key=lambda x: x.get("volume", 0))
        pairs.append((pm, best))

    return pairs


# ── Arb finders ──────────────────────────────────────────────────────────────

def find_cross_platform_arb(pairs: List[Tuple[Dict, Dict]]) -> List[Dict]:
    """
    If YES is cheaper on Polymarket and NO is cheaper on Kalshi for the
    same event, you can buy both and guarantee a profit when it resolves.

    Net profit = (1 - poly_yes - kalshi_no)  or  (1 - kalshi_yes - poly_no)
    """
    opps = []
    for pm, km in pairs:
        # Side 1: YES on Poly, NO on Kalshi
        cost1 = pm["yes"] + km["no"]
        profit1 = 1.0 - cost1

        # Side 2: YES on Kalshi, NO on Poly
        cost2 = km["yes"] + pm["no"]
        profit2 = 1.0 - cost2

        best_profit = max(profit1, profit2)
        if best_profit < 0.015:   # < 1.5% not worth it after fees
            continue

        if profit1 >= profit2:
            action = f"BUY YES on Polymarket ({pm['yes']:.2f}¢) + BUY NO on Kalshi ({km['no']:.2f}¢)"
            poly_side, kal_side = "YES", "NO"
            poly_price, kal_price = pm["yes"], km["no"]
        else:
            action = f"BUY YES on Kalshi ({km['yes']:.2f}¢) + BUY NO on Polymarket ({pm['no']:.2f}¢)"
            poly_side, kal_side = "NO", "YES"
            poly_price, kal_price = pm["no"], km["yes"]

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
    """
    Single-platform arb: YES + NO ≠ 1.0
    Buy BOTH sides for < $1, guaranteed $1 back.
    """
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
                "arb_type":    "Sum Deviation",
                "platform":    platform,
                "question":    m["question"],
                "yes":         yes,
                "no":          no,
                "sum":         round(total, 4),
                "profit_pct":  round(profit_pct, 2),
                "action":      "BUY YES + BUY NO" if dev < 0 else "SELL YES + SELL NO (short both)",
                "url":         m.get("url", ""),
                "liquidity":   m.get("liquidity", 0),
                "confidence":  min(95, int(45 + profit_pct * 12)),
                "score":       min(99, int(45 + profit_pct * 12)),
            })

    check(poly,   "Polymarket")
    check(kalshi, "Kalshi")
    opps.sort(key=lambda x: x["profit_pct"], reverse=True)
    return opps[:8]


def find_spread_opportunities(kalshi: List[Dict]) -> List[Dict]:
    """
    Wide bid/ask spreads = market-making opportunity.
    Post limit orders inside the spread to collect the edge.
    (Kalshi exposes bid/ask; Polymarket CLOB also has spreads.)
    """
    opps = []
    for m in kalshi:
        spread = m.get("spread")
        if spread is None or spread < 0.03:   # < 3¢ spread not juicy
            continue
        mid = (m["yes_bid"] + m["yes_ask"]) / 2
        opps.append({
            "arb_type":  "Spread / Market Making",
            "platform":  "Kalshi",
            "question":  m["question"],
            "yes_bid":   m["yes_bid"],
            "yes_ask":   m["yes_ask"],
            "spread":    round(spread * 100, 1),
            "mid":       round(mid * 100, 1),
            "action":    f"Post YES bid at {int(m['yes_bid']*100+1)}¢, YES ask at {int(m['yes_ask']*100-1)}¢",
            "url":       m.get("url", ""),
            "volume":    m.get("volume", 0),
            "score":     min(99, int(40 + spread * 400)),
            "confidence": min(90, int(40 + spread * 300)),
        })

    opps.sort(key=lambda x: x["spread"], reverse=True)
    return opps[:6]


# ── Master runner ─────────────────────────────────────────────────────────────

async def find_all_arb() -> Dict:
    """Run all arb detectors concurrently."""
    poly_data, kal_data = await asyncio.gather(
        poly_markets(300),
        kalshi_markets(200),
        return_exceptions=True
    )

    poly   = poly_data   if not isinstance(poly_data,  Exception) else []
    kalshi = kal_data    if not isinstance(kal_data,   Exception) else []

    pairs          = _match_markets(poly, kalshi)
    cross_platform = find_cross_platform_arb(pairs)
    sum_dev        = find_sum_deviation_arb(poly, kalshi)
    spreads        = find_spread_opportunities(kalshi)

    total = len(cross_platform) + len(sum_dev) + len(spreads)

    return {
        "cross_platform":     cross_platform,
        "sum_deviation":      sum_dev,
        "spread_making":      spreads,
        "matched_pairs":      len(pairs),
        "poly_markets":       len(poly),
        "kalshi_markets":     len(kalshi),
        "total_opportunities": total,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }
