"""
Insider / Sharp Money Detection — FIXED
Uses correct polymarket.py imports (get_active_markets, get_recent_trades_clob)
"""

import asyncio
import logging
from typing import List, Dict
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from services.polymarket import get_active_markets, get_recent_trades_clob

logger = logging.getLogger(__name__)


async def find_sharp_money_markets(markets: List[Dict]) -> List[Dict]:
    """
    Vol/Liq ratio > 0.8x = someone hammering a side hard.
    Extreme prices + high ratio = strong insider signal.
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
        extreme = yes < 0.15 or yes > 0.85
        score = min(99, int(45 + ratio * 25 + (15 if extreme else 0)))

        sharp.append({
            **m,
            "signal_type":   "Sharp Money Detected",
            "vol_liq_ratio": round(ratio, 2),
            "extreme_price": extreme,
            "score":         score,
            "note":          (
                f"{'Extreme price + ' if extreme else ''}"
                f"Vol/Liq = {ratio:.1f}x — informed traders may be piling in"
            ),
        })

    sharp.sort(key=lambda x: x["vol_liq_ratio"], reverse=True)
    return sharp[:10]


async def find_whale_repeated_markets(
    recent_trades: List[Dict], markets: List[Dict]
) -> List[Dict]:
    """
    Addresses that placed multiple large trades on the same market.
    Whale with conviction, or insider accumulating position.
    """
    address_market: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for t in recent_trades:
        if t.get("value_usd", 0) < 200:
            continue
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
                "signal_type":  "Whale Accumulation",
                "address":      f"{addr[:6]}...{addr[-4:]}",
                "full_address": addr,
                "market_id":    market_id,
                "question":     market.get("question", market_id[:40]),
                "trade_count":  len(trades),
                "total_value":  round(total_value, 2),
                "side":         trades[-1]["side"],
                "latest_price": trades[-1]["price"],
                "url":          market.get("url", ""),
                "score":        min(99, int(55 + min(total_value / 500, 30))),
                "note":         f"Wallet placed {len(trades)} trades totalling ${total_value:,.0f}",
            })

    signals.sort(key=lambda x: x["total_value"], reverse=True)
    return signals[:8]


async def find_late_resolution_bets(markets: List[Dict]) -> List[Dict]:
    """
    Markets resolving within 7 days with high 24h volume.
    Classic insider timing pattern.
    """
    now     = datetime.now(timezone.utc)
    cutoff  = now + timedelta(days=7)
    signals = []

    for m in markets:
        end_str = m.get("end_date", "")
        if not end_str:
            continue
        try:
            # Handle both Z-suffix and +00:00
            end_str_clean = end_str.replace("Z", "+00:00")
            end = datetime.fromisoformat(end_str_clean)
            # Make tz-aware if naive
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if end > cutoff or end <= now:
            continue

        v24 = m.get("volume_24h", 0)
        if v24 < 1000:
            continue

        days_left    = max(0.1, (end - now).total_seconds() / 86400)
        urgency_score = min(40, int(v24 / 200))
        time_score    = max(0, int((7 - days_left) * 4))
        score         = min(99, 45 + urgency_score + time_score)

        signals.append({
            **m,
            "signal_type": "Late Resolution Bet",
            "days_left":   round(days_left, 1),
            "score":       score,
            "note":        f"Resolves in {days_left:.1f}d — ${v24:,.0f} traded today",
        })

    signals.sort(key=lambda x: x["score"], reverse=True)
    return signals[:8]


async def find_large_trades(min_value: float = 500) -> List[Dict]:
    """Fetch large recent trades from CLOB."""
    trades = await get_recent_trades_clob(limit=100)
    large  = [t for t in trades if t.get("value_usd", 0) >= min_value]
    large.sort(key=lambda x: x["value_usd"], reverse=True)
    return large[:10]


async def get_all_insider_signals() -> Dict:
    """Run all insider detectors concurrently."""
    markets, large_trades = await asyncio.gather(
        get_active_markets(300),
        find_large_trades(500),
        return_exceptions=True
    )
    if isinstance(markets,      Exception): markets      = []
    if isinstance(large_trades, Exception): large_trades = []

    sharp_markets, whale_markets, late_bets = await asyncio.gather(
        find_sharp_money_markets(markets),
        find_whale_repeated_markets(large_trades, markets),
        find_late_resolution_bets(markets),
        return_exceptions=True
    )
    if isinstance(sharp_markets, Exception): sharp_markets = []
    if isinstance(whale_markets, Exception): whale_markets = []
    if isinstance(late_bets,     Exception): late_bets     = []

    return {
        "large_trades":  large_trades,
        "sharp_markets": sharp_markets,
        "whale_markets": whale_markets,
        "late_bets":     late_bets,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }
