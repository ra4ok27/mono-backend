import os
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import db  # SQLite helpers

# -----------------------------
# LOAD ENV
# -----------------------------
ENV = os.getenv("ENV", "local")
if ENV == "production":
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNELS_BY_AMOUNT = {
    950: int(os.getenv("CHANNEL_ID_950", "0")),
    1750: int(os.getenv("CHANNEL_ID_1750", "0")),
}

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

db.init_db()


# -----------------------------
# COMMANDS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message else ""
    parts = (text or "").split(maxsplit=1)

    # /start без параметра
    if len(parts) < 2:
        await update.message.reply_text(
            "👋 Привіт!\n"
            "Після оплати натисни кнопку «Отримати доступ» на сайті — вона відкриє бота з твоїм замовленням."
        )
        return

    order_id = parts[1].strip()

    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Замовлення не знайдено.")
        return

    if order["status"] != "paid":
        await update.message.reply_text(
            "⏳ Оплата ще не підтверджена.\n"
            "Спробуй ще раз через 10–30 секунд."
        )
        return

    # атомарно: якщо вже claimed — вдруге не дамо
    if not db.claim_once(order_id):
        await update.message.reply_text("ℹ️ Доступ вже був виданий раніше.")
        return

    amount = int(order["amount"])
    channel_id = CHANNELS_BY_AMOUNT.get(amount)

    if not channel_id:
        await update.message.reply_text("❌ Невідомий тариф.")
        return

    invite = await context.bot.create_chat_invite_link(
        chat_id=channel_id,
        member_limit=1,
    )

    await update.message.reply_text(
        f"✅ Оплата підтверджена: {amount} грн\n"
        f"🔗 Ось твоє одноразове посилання у закритий канал:\n{invite.invite_link}"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
