import os
import uuid
import requests

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

import db  # <- SQLite helpers

# -----------------------------
# LOAD ENV
# -----------------------------
ENV = os.getenv("ENV", "local")

if ENV == "production":
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

app = FastAPI()
db.init_db()  # <- create orders.db + table if not exists

# -----------------------------
# ENV
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # поки лишаємо, бо в тебе є перевірки
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
MONO_X_TOKEN = os.getenv("MONO_X_TOKEN")

# Публічний base URL для webhook'а (ngrok зараз, потім буде домен/сервер)
PUBLIC_BASE_URL = os.getenv(
    "PUBLIC_BASE_URL",
    "https://uninstrumental-dayfly-angele.ngrok-free.dev"
).rstrip("/")

# (опційно) тестовий токен для захисту тест-ендпойнта
TEST_TOKEN = os.getenv("TEST_TOKEN", "")  # в проді можна прибрати

if not BOT_TOKEN:
    raise RuntimeError("ENV BOT_TOKEN is missing")

if not ADMIN_CHAT_ID:
    raise RuntimeError("ENV ADMIN_CHAT_ID is missing")

if not MONO_X_TOKEN:
    raise RuntimeError("ENV MONO_X_TOKEN is missing")

# -----------------------------
# ROUTES
# -----------------------------
@app.get("/")
async def root():
    return {"status": "ok", "message": "Mono backend is running"}


# -----------------------------
# ✅ TEST ROUTE — ШТУЧНО СТАВИМО paid (ПОТІМ ВИДАЛИШ)
# -----------------------------
class TestMarkPaidRequest(BaseModel):
    order_id: str
    amount: int | None = None  # можна не передавати


@app.post("/test/mark-paid")
async def test_mark_paid(body: TestMarkPaidRequest, request: Request):
    # Легка "захистка": або локально, або з X-Test-Token
    client_ip = request.client.host if request.client else ""
    header_token = request.headers.get("x-test-token", "")

    if client_ip not in ("127.0.0.1", "localhost", "::1"):
        if not TEST_TOKEN or header_token != TEST_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden (test endpoint)")

    order = db.get_order(body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # поставимо paid
    if body.amount is not None:
        db.set_paid(body.order_id, int(body.amount))
    else:
        db.set_paid(body.order_id)

    return {"status": "ok", "order_id": body.order_id, "order": db.get_order(body.order_id)}


# -----------------------------
# 🔹 WEBHOOK ВІД MONO (ставимо paid) — НАДІЙНО
# -----------------------------
@app.post("/mono/webhook")
async def mono_webhook(request: Request):
    payload = await request.json()
    print("📩 MONO WEBHOOK PAYLOAD:", payload)

    data = payload.get("data") or payload

    status = data.get("status")
    amount_cents = data.get("amount")

    reference = (
        data.get("reference")
        or (data.get("merchantPaymInfo") or {}).get("reference")
        or (data.get("merchantPaymInfo") or {}).get("referenceId")
    )

    if reference is None:
        print("⚠️ NO reference in webhook payload")
        return {"status": "ok"}

    amount_uah = None
    if isinstance(amount_cents, int):
        amount_uah = round(amount_cents / 100)

    if status == "success":
        db.set_paid(reference, amount_uah)
        print(f"✅ ORDER PAID: {reference} amount={amount_uah}")

    return {"status": "ok"}


# -----------------------------
# 🔹 СТВОРЕННЯ ОПЛАТИ
# -----------------------------
MONO_API_URL = "https://api.monobank.ua/api/merchant/invoice/create"


def _validate_amount(amount: int) -> int:
    try:
        amount = int(amount)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid amount")

    if amount not in (950, 1750):
        raise HTTPException(status_code=400, detail="Invalid amount (allowed: 950, 1750)")
    return amount


@app.post("/mono/create-invoice")
def create_invoice(data: dict):
    amount = _validate_amount(data.get("amount", 0))

    order_id = f"order_{uuid.uuid4().hex}"

    # ✅ пишемо в SQLite (а не в память)
    db.upsert_order(order_id=order_id, amount=amount, status="pending")

    payload = {
        "amount": amount * 100,
        "merchantPaymInfo": {
            "reference": order_id,
            "destination": f"Оплата FullBody {amount} грн",
        },
        # ✅ ПІСЛЯ ОПЛАТИ КИДАЄ НА ТВОЮ СТОРІНКУ + order_id
        "redirectUrl": f"https://nvkv-training.com.ua/dyakuyu?order_id={order_id}",
        "webHookUrl": f"{PUBLIC_BASE_URL}/mono/webhook",
    }

    headers = {
        "X-Token": MONO_X_TOKEN,
        "Content-Type": "application/json",
    }

    r = requests.post(MONO_API_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    mono_data = r.json()

    return {"order_id": order_id, "payUrl": mono_data["pageUrl"]}


# -----------------------------
# ✅ НОВИЙ РОУТ: /pay?amount=950 або /pay?amount=1750
#     Створює інвойс і одразу редіректить на оплату Mono
# -----------------------------
@app.get("/pay")
def pay(amount: int = Query(..., description="Allowed: 950 or 1750")):
    amount = _validate_amount(amount)
    result = create_invoice({"amount": amount})
    return RedirectResponse(url=result["payUrl"], status_code=302)
