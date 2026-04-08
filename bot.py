"""
Polymarket / Kalshi Intel Bot
Railway-ready entry point
"""

import logging
import os
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

from handlers.start     import start_handler, help_handler
from handlers.arbitrage import arb_handler, arb_callback
from handlers.bets      import bets_handler, bets_callback
from handlers.insider   import insider_handler, insider_callback
from handlers.alerts    import alerts_handler, alerts_toggle
from services.scheduler import start_scheduler

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update error:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Something went wrong. Try again shortly.")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("❌  TELEGRAM_BOT_TOKEN env var not set")

    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start",   start_handler))
    app.add_handler(CommandHandler("help",    help_handler))
    app.add_handler(CommandHandler("arb",     arb_handler))
    app.add_handler(CommandHandler("bets",    bets_handler))
    app.add_handler(CommandHandler("insider", insider_handler))
    app.add_handler(CommandHandler("alerts",  alerts_handler))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(arb_callback,     pattern="^arb_"))
    app.add_handler(CallbackQueryHandler(bets_callback,    pattern="^bets_"))
    app.add_handler(CallbackQueryHandler(insider_callback, pattern="^insider_"))
    app.add_handler(CallbackQueryHandler(alerts_handler,   pattern="^alerts_menu$"))
    app.add_handler(CallbackQueryHandler(alerts_toggle,    pattern="^alerts_(master|arb|signals|insider)$"))

    app.add_error_handler(error_handler)
    start_scheduler(app)

    logger.info("🚀 Polymarket Intel Bot polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
