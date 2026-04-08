from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.insider import get_all_insider_signals
from utils.formatting import usd, cents, score_emoji, score_bar, trunc, div


async def insider_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🕵️ All Insider",     callback_data="insider_all"),
         InlineKeyboardButton("💰 Large Trades",    callback_data="insider_trades")],
        [InlineKeyboardButton("🦈 Sharp Money",     callback_data="insider_sharp"),
         InlineKeyboardButton("🐋 Whale Bets",      callback_data="insider_whales")],
        [InlineKeyboardButton("⏰ Late Bets",        callback_data="insider_late")],
    ]
    await update.message.reply_text(
        "🕵️ *Insider / Sharp Money Detector*\nChoose type:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


async def insider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Scanning for sharp money…")

    data = await get_all_insider_signals()
    mode = q.data

    if mode == "insider_trades":
        items = data["large_trades"]
        title = "💰 *LARGE RECENT TRADES*"
        render = _render_trade
    elif mode == "insider_sharp":
        items = data["sharp_markets"]
        title = "🦈 *SHARP MONEY MARKETS*"
        render = _render_sharp
    elif mode == "insider_whales":
        items = data["whale_markets"]
        title = "🐋 *WHALE ACCUMULATION*"
        render = _render_whale
    elif mode == "insider_late":
        items = data["late_bets"]
        title = "⏰ *LATE RESOLUTION BETS* (insiders time late)"
        render = _render_late
    else:
        # All — top items from each
        combined = (
            data["sharp_markets"][:3] +
            data["whale_markets"][:3] +
            data["late_bets"][:2]
        )
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        items = combined
        title = "🕵️ *INSIDER INTELLIGENCE*"
        render = _render_any

    lines = [f"{title}\n{div()}"]

    if not items:
        lines.append("\n📭 No sharp signals detected right now.")
    else:
        for it in items[:7]:
            lines.append(render(it))

    lines.append(f"\n{div()}\n_Sharp ≠ guaranteed. Always verify independently._")
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data=mode)]]
    try:
        await q.edit_message_text(
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
            disable_web_page_preview=True
        )
    except Exception:
        await q.edit_message_text("\n".join(lines[:18]), parse_mode="Markdown",
                                  disable_web_page_preview=True)


def _render_trade(t: dict) -> str:
    side_em = "🟢" if t["side"] == "BUY" else "🔴"
    return (
        f"\n{side_em} `{t['side']}` @ `{cents(t['price'])}` — `{usd(t['value_usd'])}`\n"
        f"  Taker: `{t['taker'][:6]}…{t['taker'][-4:] if len(t['taker']) > 10 else '?'}`\n"
        f"  Time: `{str(t['timestamp'])[:16]}`"
    )


def _render_sharp(m: dict) -> str:
    em = score_emoji(m["score"])
    return (
        f"\n{em} 🟣 _{trunc(m['question'])}_\n"
        f"  YES: `{cents(m['yes'])}` | Vol/Liq: `{m['vol_liq_ratio']:.1f}x`\n"
        f"  {m['note']}\n"
        f"  Score: `{score_bar(m['score'])}` {m['score']}/100\n"
        f"  [Polymarket]({m.get('url', '')})"
    )


def _render_whale(w: dict) -> str:
    em = score_emoji(w["score"])
    side_em = "🟢" if w["side"] == "BUY" else "🔴"
    return (
        f"\n{em} 🐋 _{trunc(w['question'])}_\n"
        f"  Wallet: `{w['address']}` placed `{w['trade_count']}` trades\n"
        f"  Total: `{usd(w['total_value'])}` {side_em} {w['side']} @ `{cents(w['latest_price'])}`\n"
        f"  {w['note']}\n"
        f"  [Polymarket]({w.get('url', '')})"
    )


def _render_late(m: dict) -> str:
    em = score_emoji(m["score"])
    return (
        f"\n{em} ⏰ _{trunc(m['question'])}_\n"
        f"  YES: `{cents(m['yes'])}` | Resolves in `{m['days_left']}d`\n"
        f"  {m['note']}\n"
        f"  Score: `{score_bar(m['score'])}` {m['score']}/100\n"
        f"  [Polymarket]({m.get('url', '')})"
    )


def _render_any(m: dict) -> str:
    em = score_emoji(m.get("score", 50))
    sig = m.get("signal_type", "")
    return (
        f"\n{em} _{trunc(m.get('question', '?'))}_\n"
        f"  {sig} | Score: `{m.get('score', '?')}/100`\n"
        f"  [View]({m.get('url', '')})"
    )
