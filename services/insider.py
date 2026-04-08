"""
Insider / Sharp Money Detection
Detects unusual betting patterns that suggest informed traders:
  1. Sudden large-volume buys on illiquid markets
  2. Price moving sharply against consensus
  3. Big trades close to resolution date (insider timing)
  4. Whale wallets buying the same market repeatedly
  5. Markets where volume >> liquidity (sharp money piling in)
"""

import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from services.polymarket import get_active_markets, get_market_trades, GAMMA_BASE

logger = logging.getLogger(__name__)


async def _get(session, url, params=None):
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=12)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.warning(f"GET {url}: {e}")
    return None


async def get_recent_large_trades(min_size_usd: float = 500) -> List[Dict]:
    """
    Fetch the most recent large trades across all Polymarket markets.
    Large = someone put serious money on one side.
    """
    async with aiohttp.ClientSession() as s:
        params = {"limit": 100, "order": "TIMESTAMP", "ascending": "false"}
        data = await _get(s, f"https://clob.polymarket.com/trades", params)
        if not data:
            return []

        trades = data if isinstance(data, list) else data.get("trades", [])
        large = []
        for t in trades:
            size = float(t.get("size", 0) or 0)
            price = float(t.get("price", 0) or 0)
            value = size * price
            if value < min_size_usd:
                continue
            large.append({
                "market_id":  t.get("market", ""),
                "side":       t.get("side", ""),
                "price":      round(price, 3),
                "size":       round(size, 2),
                "value_usd":  round(value, 2),
                "timestamp":  t.get("timestamp", ""),
                "maker":      t.get("maker_address", ""),
                "taker":      t.get("taker_address", ""),
            })
        return large


async def find_sharp_money_markets(markets: List[Dict]) -> List[Dict]:
    """
    Sharp money signal: markets where 24h volume is suspiciously high
    relative to total liquidity — someone is hammering a side hard.
    vol/liq > 2.0 with price moving > 5% in 24h = sharp money.
    """
    sharp = []
    for m in markets:
        liq = m.get("liquidity", 0)
        v24 = m.get("volume_24h", 0)
        if liq < 1000 or v24 < 500:
            continue

        ratio = v24 / max(liq, 1)
        if ratio < 0.8:
            continue

        yes = m["yes"]
        # Markets where price is being pushed toward extremes = sharp bet
        extreme = yes < 0.15 or yes > 0.85
        score = min(99, int(45 + ratio * 25 + (15 if extreme else 0)))

        sharp.append({
            **m,
            "signal_type":  "Sharp Money Detected",
            "vol_liq_ratio": round(ratio, 2),
            "extreme_price": extreme,
            "score":         score,
            "note":          (
                f"{'Extreme price' if extreme else 'High'} vol/liq ratio {ratio:.1f}x — "
                f"informed traders may be piling in"
            ),
        })

    sharp.sort(key=lambda x: x["vol_liq_ratio"], reverse=True)
    return sharp[:10]


async def find_whale_repeated_markets(recent_trades: List[Dict], markets: List[Dict]) -> List[Dict]:
    """
    Find addresses that placed multiple large trades on the same market
    — whales with conviction, or insiders accumulating.
    """
    from collections import defaultdict
    address_market: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for t in recent_trades:
        for addr in [t.get("maker", ""), t.get("taker", "")]:
            if addr and len(addr) > 10:
                address_market[addr][t["market_id"]].append(t)

    market_lookup = {m["condition_id"]: m for m in markets if m.get("condition_id")}
    signals = []

    for addr, market_trades in address_market.items():
        for market_id, trades in market_trades.items():
            if len(trades) < 2:
                continue
            total_value = sum(t["value_usd"] for t in trades)
            if total_value < 1000:
                continue

            market = market_lookup.get(market_id, {})
            signals.append({
                "signal_type":   "Whale Accumulation",
                "address":       f"{addr[:6]}...{addr[-4:]}",
                "full_address":  addr,
                "market_id":     market_id,
                "question":      market.get("question", market_id),
                "trade_count":   len(trades),
                "total_value":   round(total_value, 2),
                "side":          trades[-1]["side"],
                "latest_price":  trades[-1]["price"],
                "url":           market.get("url", ""),
                "score":         min(99, int(55 + min(total_value / 500, 30))),
                "note":          f"Wallet placed {len(trades)} trades totalling ${total_value:,.0f}",
            })

    signals.sort(key=lambda x: x["total_value"], reverse=True)
    return signals[:8]


async def find_late_resolution_bets(markets: List[Dict]) -> List[Dict]:
    """
    Markets resolving within 7 days with unusually high 24h volume.
    Insiders tend to bet close to resolution when they have information.
    """
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=7)
    signals = []

    for m in markets:
        end_str = m.get("end_date", "")
        if not end_str:
            continue
        try:
            end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if end > cutoff or end < now:
            continue

        days_left = max(0.1, (end - now).total_seconds() / 86400)
        v24 = m.get("volume_24h", 0)
        if v24 < 1000:
            continue

        urgency_score = min(40, int(v24 / 200))
        time_score    = max(0, int((7 - days_left) * 4))
        score = min(99, 45 + urgency_score + time_score)

        signals.append({
            **m,
            "signal_type": "Late Resolution Bet",
            "days_left":   round(days_left, 1),
            "score":       score,
            "note":        f"Resolves in {days_left:.1f} days — ${v24:,.0f} traded today",
        })

    signals.sort(key=lambda x: x["score"], reverse=True)
    return signals[:8]


async def get_all_insider_signals() -> Dict:
    """Run all insider detectors."""
    markets = await get_active_markets(300)

    large_trades, sharp_markets, late_bets = await asyncio.gather(
        get_recent_large_trades(500),
        find_sharp_money_markets(markets),
        find_late_resolution_bets(markets),
        return_exceptions=True
    )

    if isinstance(large_trades,  Exception): large_trades  = []
    if isinstance(sharp_markets, Exception): sharp_markets = []
    if isinstance(late_bets,     Exception): late_bets     = []

    whale_markets = await find_whale_repeated_markets(
        large_trades if large_trades else [], markets
    )

    return {
        "large_trades":   large_trades[:10],
        "sharp_markets":  sharp_markets,
        "whale_markets":  whale_markets,
        "late_bets":      late_bets,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
    }
