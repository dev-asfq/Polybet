from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.arbitrage import find_all_arb
from utils.formatting import usd, pct, cents, score_emoji, score_bar, platform_emoji, trunc, div


async def arb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🔀 All Arb", callback_data="arb_all"),
         InlineKeyboardButton("⚔️ Cross-Platform", callback_data="arb_cross")],
        [InlineKeyboardButton("📐 Sum Deviation", callback_data="arb_sum"),
         InlineKeyboardButton("📈 Spread / MM", callback_data="arb_spread")],
    ]
    await update.message.reply_text(
        "🔀 *Arbitrage Scanner*\nChoose type:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def arb_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("⏳ Scanning both platforms…")

    data = await find_all_arb()
    mode = q.data  # arb_all / arb_cross / arb_sum / arb_spread

    if mode == "arb_cross":
        opps = data["cross_platform"]
        title = "⚔️ *CROSS-PLATFORM ARB* (Poly ↔ Kalshi)"
        _render = _render_cross
    elif mode == "arb_sum":
        opps = data["sum_deviation"]
        title = "📐 *SUM DEVIATION ARB*"
        _render = _render_sum
    elif mode == "arb_spread":
        opps = data["spread_making"]
        title = "📈 *SPREAD / MARKET MAKING*"
        _render = _render_spread
    else:
        # All arb — show best from each type
        all_opps = (
            data["cross_platform"][:3] +
            data["sum_deviation"][:3] +
            data["spread_making"][:2]
        )
        all_opps.sort(key=lambda x: x.get("score", 0), reverse=True)
        opps = all_opps
        title = (
            f"🔀 *ARB DASHBOARD*\n"
            f"Poly: `{data['poly_markets']}` mkts | "
            f"Kalshi: `{data['kalshi_markets']}` mkts | "
            f"Matched: `{data['matched_pairs']}` pairs"
        )
        _render = _render_any

    lines = [f"{title}\n{div()}"]

    if not opps:
        lines.append("\n📭 No opportunities meeting threshold right now.\n_Check back in 15 min._")
    else:
        for o in opps[:6]:
            lines.append(_render(o))

    lines.append(f"\n{div()}\n⚠️ _Fees + slippage reduce net profit. DYOR._")

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


def _render_cross(o: dict) -> str:
    em = score_emoji(o["score"])
    return (
        f"\n{em} *{o['event_topic'].upper()} — Cross-Platform*\n"
        f"  🟣 Poly: _{trunc(o['poly_question'], 55)}_\n"
        f"  🔵 Kal:  _{trunc(o['kal_question'],  55)}_\n"
        f"  Buy {o['poly_side']} on Poly @ `{cents(o['poly_price'])}` + "
        f"{o['kal_side']} on Kalshi @ `{cents(o['kal_price'])}`\n"
        f"  💰 Profit: `{pct(o['profit_pct'])}` | Confidence: `{o['confidence']}%`\n"
        f"  [Poly]({o['poly_url']}) · [Kalshi]({o['kal_url']})"
    )


def _render_sum(o: dict) -> str:
    em = score_emoji(o["score"])
    pe = platform_emoji(o["platform"])
    return (
        f"\n{em} {pe} *{o['platform']} — Sum Deviation*\n"
        f"  _{trunc(o['question'])}_\n"
        f"  YES: `{cents(o['yes'])}` + NO: `{cents(o['no'])}` = `{o['sum']:.3f}`\n"
        f"  Strategy: _{o['action']}_\n"
        f"  💰 Profit: `{pct(o['profit_pct'])}` | Liq: `{usd(o['liquidity'])}`\n"
        f"  [Open market]({o['url']})"
    )


def _render_spread(o: dict) -> str:
    em = score_emoji(o["score"])
    return (
        f"\n{em} 🔵 *Kalshi — Spread Opportunity*\n"
        f"  _{trunc(o['question'])}_\n"
        f"  Bid: `{o['yes_bid']*100:.0f}¢` | Ask: `{o['yes_ask']*100:.0f}¢` | "
        f"Spread: `{o['spread']}¢`\n"
        f"  Strategy: _{o['action']}_\n"
        f"  Vol: `{usd(o['volume'])}`\n"
        f"  [Open market]({o['url']})"
    )


def _render_any(o: dict) -> str:
    t = o.get("arb_type", "")
    if t == "Cross-Platform":    return _render_cross(o)
    if t == "Sum Deviation":     return _render_sum(o)
    if t == "Spread / Market Making": return _render_spread(o)
    return f"\n📊 {trunc(o.get('question', '?'))}\n  Profit: `{pct(o.get('profit_pct', 0))}`"
