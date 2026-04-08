from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.database import get_user, update_user


def _kb(u: dict) -> InlineKeyboardMarkup:
    def lbl(key, name):
        return f"{'✅' if u.get(key, True) else '❌'} {name}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(lbl("alerts", "🔔 Master Alerts"), callback_data="alerts_master")],
        [InlineKeyboardButton(lbl("alert_arb",     "🔀 Arb Alerts"),    callback_data="alerts_arb"),
         InlineKeyboardButton(lbl("alert_signals", "📊 Bet Alerts"),    callback_data="alerts_signals")],
        [InlineKeyboardButton(lbl("alert_insider", "🕵️ Insider Alerts"), callback_data="alerts_insider")],
    ])


def _msg(u: dict) -> str:
    mp = u.get("min_profit_pct", 2.0)
    return (
        "🔔 *Alert Settings*\n"
        "─────────────────────\n"
        f"Min arb profit threshold: `{mp:.1f}%`\n\n"
        "_Schedules when ON:_\n"
        "• Arb scanner: every **15 min**\n"
        "• Best bets: every **30 min**\n"
        "• Insider: every **60 min**"
    )


async def alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u = get_user(uid)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(_msg(u), parse_mode="Markdown", reply_markup=_kb(u))
    else:
        await update.message.reply_text(_msg(u), parse_mode="Markdown", reply_markup=_kb(u))


async def alerts_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    key_map = {
        "alerts_master":  "alerts",
        "alerts_arb":     "alert_arb",
        "alerts_signals": "alert_signals",
        "alerts_insider": "alert_insider",
    }
    key = key_map.get(q.data)
    if key:
        update_user(uid, {key: not u.get(key, True)})
        u = get_user(uid)
    await q.edit_message_text(_msg(u), parse_mode="Markdown", reply_markup=_kb(u))
