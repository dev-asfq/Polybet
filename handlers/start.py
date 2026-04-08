from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.database import get_user

WELCOME = """
🎯 *Prediction Market Intel Bot*

Sharp signals for *Polymarket* & *Kalshi* bettors.

*What I track:*
🔀 `/arb` — Cross-platform & same-platform arbitrage
📊 `/bets` — Best current betting opportunities
🕵️ `/insider` — Sharp money & whale bet detection
🔔 `/alerts` — Configure your auto-alerts

Auto-alerts fire every *15 minutes* when opportunities arise.

_All data is live from Polymarket CLOB + Kalshi API._
"""

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user(update.effective_user.id)
    kb = [
        [InlineKeyboardButton("🔀 Arbitrage", callback_data="arb_all"),
         InlineKeyboardButton("📊 Best Bets", callback_data="bets_all")],
        [InlineKeyboardButton("🕵️ Insider", callback_data="insider_all"),
         InlineKeyboardButton("🔔 Alerts", callback_data="alerts_menu")],
    ]
    await update.message.reply_text(
        WELCOME, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="Markdown")
