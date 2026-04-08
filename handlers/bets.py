from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.polymarket import get_all_signals
from utils.formatting import usd, cents, pct, score_emoji, score_bar, trunc, div


async def bets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 All Best Bets",  callback_data="bets_all"),
         InlineKeyboardButton("📈 Volume Spikes",  callback_data="bets_spikes")],
        [InlineKeyboardButton("🎯 Edge Bets",       callback_data="bets_edge"),
         InlineKeyboardButton("💹 High Value",      callback_data="bets_hv")],
    ]
    await update.message.reply_text(
        "📊 *Best Bets Scanner*\nChoose type:",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )


async def bets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Scanning Polymarket…")

    signals = await get_all_signals()

    if signals.get("error"):
        await q.edit_message_text("❌ Could not reach Polymarket API. Try again shortly.")
        return

    mode = q.data
    scanned = signals["total_scanned"]

    if mode == "bets_spikes":
        items = signals["vol_spikes"]
        title = f"📈 *VOLUME SPIKES* (scanned `{scanned}` markets)"
        render = _render_spike
    elif mode == "bets_edge":
        items = signals["edge_bets"]
        title = f"🎯 *EDGE BETS* (scanned `{scanned}` markets)"
        render = _render_edge
    elif mode == "bets_hv":
        items = signals["best_bets"]
        title = f"💹 *HIGH VALUE BETS* (scanned `{scanned}` markets)"
        render = _render_hv
    else:
        # All — mix top items from each
        combined = (
            signals["vol_spikes"][:3] +
            signals["edge_bets"][:3] +
            signals["best_bets"][:4]
        )
        combined.sort(key=lambda x: x.get("score", 0), reverse=True)
        items = combined
        title = f"📊 *BEST BETS DASHBOARD* — `{scanned}` markets scanned"
        render = _render_any

    lines = [f"{title}\n{div()}"]
    if not items:
        lines.append("\n📭 No standout bets right now. Check back soon.")
    else:
        for it in items[:8]:
            lines.append(render(it))

    lines.append(f"\n{div()}\n⚠️ _Not financial advice. Prediction markets carry risk._")

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


def _render_spike(m: dict) -> str:
    em = score_emoji(m["score"])
    return (
        f"\n{em} 🟣 _{trunc(m['question'])}_\n"
        f"  YES: `{cents(m['yes'])}` | Vol 24h: `{usd(m['volume_24h'])}`\n"
        f"  Spike: `{m['spike_pct']}%` of all-time vol today\n"
        f"  Score: `{score_bar(m['score'])}` {m['score']}/100\n"
        f"  [Polymarket]({m['url']})"
    )


def _render_edge(m: dict) -> str:
    em = score_emoji(m["score"])
    return (
        f"\n{em} 🟣 _{trunc(m['question'])}_\n"
        f"  Type: `{m['edge_type']}` | YES: `{cents(m['yes'])}`\n"
        f"  {m['ev_note']}\n"
        f"  Liq: `{usd(m['liquidity'])}` | Score: `{m['score']}/100`\n"
        f"  [Polymarket]({m['url']})"
    )


def _render_hv(m: dict) -> str:
    em = score_emoji(m["score"])
    return (
        f"\n{em} 🟣 _{trunc(m['question'])}_\n"
        f"  YES: `{cents(m['yes'])}` | NO: `{cents(m['no'])}`\n"
        f"  Liq: `{usd(m['liquidity'])}` | Vol 24h: `{usd(m['volume_24h'])}`\n"
        f"  Score: `{score_bar(m['score'])}` {m['score']}/100\n"
        f"  [Polymarket]({m['url']})"
    )


def _render_any(m: dict) -> str:
    et = m.get("edge_type") or m.get("bet_type") or ""
    em = score_emoji(m["score"])
    return (
        f"\n{em} 🟣 _{trunc(m['question'])}_\n"
        f"  YES: `{cents(m['yes'])}` | Score: `{m['score']}/100`"
        + (f"\n  _{et}_" if et else "")
        + f"\n  [Polymarket]({m.get('url', '')})"
    )
