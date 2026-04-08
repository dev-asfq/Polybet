"""
Scheduler — broadcasts alerts to all subscribed users.
  - Arb:     every 15 min  (only if profit > user threshold)
  - Bets:    every 30 min  (only top signals)
  - Insider: every 60 min  (only sharp signals score > 75)
"""

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application
from telegram.error import TelegramError

from services.arbitrage  import find_all_arb
from services.polymarket import get_all_signals
from services.insider    import get_all_insider_signals
from utils.database import all_users
from utils.formatting import usd, cents, pct, score_emoji, trunc, div

logger = logging.getLogger(__name__)


async def _send(app: Application, uid: int, text: str):
    try:
        await app.bot.send_message(
            chat_id=uid, text=text,
            parse_mode="Markdown", disable_web_page_preview=True
        )
    except TelegramError as e:
        logger.warning(f"Send to {uid} failed: {e}")


async def broadcast_arb(app: Application):
    data = await find_all_arb()
    all_opps = (
        data["cross_platform"][:2] +
        data["sum_deviation"][:2]
    )
    all_opps = [o for o in all_opps if o.get("profit_pct", 0) >= 1.5]
    if not all_opps:
        return

    lines = [f"🔀 *ARB ALERT* — {len(all_opps)} opportunity/ies\n{div()}"]
    for o in all_opps[:4]:
        em = score_emoji(o["score"])
        t = o.get("arb_type", "")
        if t == "Cross-Platform":
            lines.append(
                f"\n{em} *Cross-Platform* `{o['event_topic'].upper()}`\n"
                f"  Profit: `{pct(o['profit_pct'])}` | {o['action']}\n"
                f"  [Poly]({o['poly_url']}) · [Kalshi]({o['kal_url']})"
            )
        else:
            lines.append(
                f"\n{em} *{t}* — 🟣 Polymarket\n"
                f"  _{trunc(o['question'], 60)}_\n"
                f"  Profit: `{pct(o['profit_pct'])}` | {o['action']}\n"
                f"  [Open]({o.get('url', '')})"
            )
    lines.append(f"\n{div()}\n_/arb for full details_")
    msg = "\n".join(lines)

    for u in all_users():
        if u.get("alerts") and u.get("alert_arb"):
            threshold = u.get("min_profit_pct", 2.0)
            if any(o["profit_pct"] >= threshold for o in all_opps):
                await _send(app, u["id"], msg)
                await asyncio.sleep(0.05)


async def broadcast_bets(app: Application):
    signals = await get_all_signals()
    top = sorted(
        signals.get("vol_spikes", [])[:2] + signals.get("edge_bets", [])[:2],
        key=lambda x: x.get("score", 0), reverse=True
    )
    if not top:
        return

    lines = [f"📊 *BET ALERT* — Top signals\n{div()}"]
    for m in top[:4]:
        em = score_emoji(m["score"])
        lines.append(
            f"\n{em} _{trunc(m['question'])}_\n"
            f"  YES: `{cents(m['yes'])}` | Score: `{m['score']}/100`\n"
            f"  [Polymarket]({m.get('url', '')})"
        )
    lines.append(f"\n{div()}\n_/bets for full details_")
    msg = "\n".join(lines)

    for u in all_users():
        if u.get("alerts") and u.get("alert_signals"):
            await _send(app, u["id"], msg)
            await asyncio.sleep(0.05)


async def broadcast_insider(app: Application):
    data = await get_all_insider_signals()
    sharp = [m for m in data.get("sharp_markets", []) if m.get("score", 0) >= 75]
    whales = data.get("whale_markets", [])[:2]
    items = (sharp[:2] + whales)
    if not items:
        return

    lines = [f"🕵️ *INSIDER ALERT*\n{div()}"]
    for m in items[:4]:
        em = score_emoji(m.get("score", 70))
        lines.append(
            f"\n{em} _{trunc(m.get('question', '?'))}_\n"
            f"  {m.get('signal_type', '')} | Score: `{m.get('score', '?')}/100`\n"
            f"  [Polymarket]({m.get('url', '')})"
        )
    lines.append(f"\n{div()}\n_/insider for full details_")
    msg = "\n".join(lines)

    for u in all_users():
        if u.get("alerts") and u.get("alert_insider"):
            await _send(app, u["id"], msg)
            await asyncio.sleep(0.05)


def start_scheduler(app: Application):
    scheduler = AsyncIOScheduler()

    scheduler.add_job(lambda: asyncio.ensure_future(broadcast_arb(app)),
                      "interval", minutes=15, id="arb")
    scheduler.add_job(lambda: asyncio.ensure_future(broadcast_bets(app)),
                      "interval", minutes=30, id="bets")
    scheduler.add_job(lambda: asyncio.ensure_future(broadcast_insider(app)),
                      "interval", minutes=60, id="insider")

    scheduler.start()
    logger.info("✅ Scheduler started — arb:15m | bets:30m | insider:60m")
