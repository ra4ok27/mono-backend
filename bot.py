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
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")

# ТЕСТ: 200 = канал 950
CHANNEL_ID_200 = os.getenv("CHANNEL_ID_200") or os.getenv("CHANNEL_ID_950")
CHANNEL_ID_1750 = os.getenv("CHANNEL_ID_1750")

INVITE_TTL_SECONDS = int(os.getenv("INVITE_TTL_SECONDS", "600"))  # 10 хв

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not BACKEND_URL:
    raise RuntimeError("BACKEND_URL missing")

if not CHANNEL_ID_200:
    raise RuntimeError("CHANNEL_ID_200 (or CHANNEL_ID_950) missing")

if not CHANNEL_ID_1750:
    raise RuntimeError("CHANNEL_ID_1750 missing")


def _pick_channel_id(amount: int) -> int:
    if amount == 200:
        return int(CHANNEL_ID_200)
    if amount == 1750:
        return int(CHANNEL_ID_1750)
    raise ValueError(f"Unknown amount: {amount}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args

    # /start без параметрів
    if not args:
        await update.message.reply_text(
            "✅ Бот працює.\n\n"
            "Після оплати натисни кнопку на сторінці «Дякую» — "
            "вона відкриє цього бота з твоїм токеном."
        )
        return

    token = args[0].strip()

    # 1) просимо бекенд підтвердити токен + “спалити” його (claimed=1)
    try:
        r = requests.post(
            f"{BACKEND_URL}/tg/claim",
            json={"token": token, "chat_id": chat_id},
            timeout=25,
        )
    except requests.exceptions.RequestException:
        await update.message.reply_text(
            "❌ Не можу підключитись до сервера.\n"
            "Спробуй ще раз через 20–30 секунд."
        )
        return

    if r.status_code != 200:
        try:
            detail = r.json().get("detail", "Помилка")
        except Exception:
            detail = r.text or "Помилка"

        await update.message.reply_text(
            f"⏳ Поки що не можу видати доступ: {detail}\n\n"
            "Якщо ти щойно оплатив — зачекай 10–30 секунд і натисни кнопку на сторінці «Дякую» ще раз."
        )
        return

    data = r.json()
    amount = int(data.get("amount") or 0)

    # 2) створюємо ОДНОРАЗОВИЙ інвайт (1 використання) + TTL
    channel_id = _pick_channel_id(amount)
    expire_dt = datetime.now(timezone.utc) + timedelta(seconds=INVITE_TTL_SECONDS)

    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,          # ✅ 1 використання
            expire_date=expire_dt,   # ✅ згорає по часу
        )
    except Exception as e:
        await update.message.reply_text(
            "❌ Не можу створити одноразове запрошення.\n\n"
            "Перевір, що бот доданий адміном в канал і має право: «Invite users / Додавати підписників».\n"
            f"Тех. деталь: {e}"
        )
        return

    await update.message.reply_text(
        "✅ Оплату підтверджено!\n"
        "Ось твоє ОДНОРАЗОВЕ запрошення (працює 1 раз і згорає по часу):\n\n"
        f"{invite.invite_link}"
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
