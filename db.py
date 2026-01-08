# db.py
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

DB_PATH = Path(__file__).resolve().parent / "orders.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db() -> None:
    """
    Створюємо таблицю + робимо легкі міграції:
    - додаємо access_token, якщо його нема
    - додаємо claimed, якщо його нема (на випадок старої БД)
    """
    with _connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id     TEXT PRIMARY KEY,
            amount       INTEGER NOT NULL,
            status       TEXT NOT NULL,
            claimed      INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.commit()

        # --- migrations: add missing columns without dropping table ---
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(orders);").fetchall()
        }

        if "access_token" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN access_token TEXT;")

        if "claimed" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN claimed INTEGER NOT NULL DEFAULT 0;")

        conn.commit()


def upsert_order(order_id: str, amount: int, status: str) -> None:
    with _connect() as conn:
        conn.execute("""
        INSERT INTO orders (order_id, amount, status, claimed)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(order_id) DO UPDATE SET
            amount=excluded.amount,
            status=excluded.status;
        """, (order_id, int(amount), status))
        conn.commit()


def set_paid(order_id: str, amount: Optional[int] = None) -> None:
    """
    ВАЖЛИВО:
    amount у нас = тариф (950/1750). Його НЕ можна перезатирати.
    Тому тут просто ставимо status='paid' і ігноруємо amount.
    """
    with _connect() as conn:
        conn.execute("UPDATE orders SET status='paid' WHERE order_id=?;", (order_id,))
        conn.commit()


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT order_id, amount, status, claimed, access_token FROM orders WHERE order_id=?;",
            (order_id,)
        ).fetchone()
        return dict(row) if row else None


# -----------------------------
# ✅ НОВЕ: токен-флоу
# -----------------------------
def set_token(order_id: str, token: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE orders SET access_token=? WHERE order_id=?;",
            (token, order_id)
        )
        conn.commit()


def get_order_by_token(token: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT order_id, amount, status, claimed, access_token FROM orders WHERE access_token=?;",
            (token,)
        ).fetchone()
        return dict(row) if row else None


def claim_once_by_token(token: str) -> bool:
    """
    True  -> успішно заклеймили (paid + claimed=0) по access_token
    False -> або не paid, або вже claimed, або token нема
    """
    with _connect() as conn:
        cur = conn.execute("""
            UPDATE orders
            SET claimed=1
            WHERE access_token=?
              AND status='paid'
              AND claimed=0;
        """, (token,))
        conn.commit()
        return cur.rowcount == 1


# -----------------------------
# ✅ ЗАЛИШАЄМО СТАРЕ (щоб нічого не ламати)
# -----------------------------
def claim_once(order_id: str) -> bool:
    """
    True  -> успішно заклеймили (paid + claimed=0)
    False -> або не paid, або вже claimed, або order нема
    """
    with _connect() as conn:
        cur = conn.execute("""
            UPDATE orders
            SET claimed=1
            WHERE order_id=?
              AND status='paid'
              AND claimed=0;
        """, (order_id,))
        conn.commit()
        return cur.rowcount == 1
