import os
import requests
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# -----------------------------
# LOAD ENV
# -----------------------------
load_dotenv(override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "https://mono-backend-ydmr.onrender.com").rstrip("/")

CHANNEL_ID_950 = os.getenv("CHANNEL_ID_950", "").strip()
CHANNEL_ID_1750 = os.getenv("CHANNEL_ID_1750", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")
if not BACKEND_URL:
    raise RuntimeError("BACKEND_URL missing")
if not CHANNEL_ID_950:
    raise RuntimeError("CHANNEL_ID_950 missing")
if not CHANNEL_ID_1750:
    raise RuntimeError("CHANNEL_ID_1750 missing")

CHANNEL_ID_950_INT = int(CHANNEL_ID_950)
CHANNEL_ID_1750_INT = int(CHANNEL_ID_1750)

# -----------------------------
# HELPERS
# -----------------------------
def _pick_channel_id(amount: int) -> int:
    """
    🔧 ТЕСТОВА ЛОГІКА:
    200 грн = тестовий тариф замість 950
    1750 грн = преміум
    """
    if int(amount) == 1750:
        return CHANNEL_ID_1750_INT
    return CHANNEL_ID_950_INT  # 200 або 950 → канал 950


async def _create_one_time_invite(context: ContextTypes.DEFAULT_TYPE, channel_id: int) -> str:
    """
    Створює інвайт:
    - 1 використання
    - діє 10 хв
    """
    expire_dt = datetime.now(timezone.utc) + timedelta(minutes=10)

    invite = await context.bot.create_chat_invite_link(
        chat_id=channel_id,
        member_limit=1,
        expire_date=expire_dt,
    )
    return invite.invite_link


# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    # /start без параметрів
    if not args:
        await update.message.reply_text(
            "✅ Бот працює.\n\n"
            "Після оплати натисни кнопку на сайті «Отримати доступ у Telegram» — "
            "вона відкриє цього бота з твоїм одноразовим токеном."
        )
        return

    token = (args[0] or "").strip()

    if not token:
        await update.message.reply_text(
            "Натисни кнопку оплати на сайті і повернись сюди через кнопку зі сторінки «Дякую» ✅"
        )
        return

    try:
        r = requests.post(
            f"{BACKEND_URL}/tg/claim",
            json={"token": token, "chat_id": chat_id},
            timeout=25,
        )

        if r.status_code == 200:
            data = r.json()
            amount = int(data.get("amount") or 0)

            channel_id = _pick_channel_id(amount)
            invite_link = await _create_one_time_invite(context, channel_id)

            await update.message.reply_text(
                f"✅ Оплату підтверджено ({amount} грн).\n\n"
                f"Ось твій персональний доступ "
                f"(1 вхід, діє 10 хв):\n{invite_link}"
            )
            return

        if r.status_code == 409:
            await update.message.reply_text("⚠️ Цей токен уже був використаний.")
            return

        if r.status_code == 404:
            await update.message.reply_text(
                "❌ Токен не знайдено.\n"
                "Перейди з кнопки на сторінці «Дякую» ще раз."
            )
            return

        try:
            detail = r.json().get("detail", "Помилка")
        except Exception:
            detail = r.text or "Помилка"

        await update.message.reply_text(
            f"⏳ Поки що не можу видати доступ: {detail}\n\n"
            "Якщо ти щойно оплатив — зачекай 10–30 секунд і натисни це саме посилання ще раз."
        )

    except requests.exceptions.RequestException:
        await update.message.reply_text(
            "❌ Зараз не можу підключитись до сервера.\n"
            "Спробуй ще раз через 30 секунд."
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
