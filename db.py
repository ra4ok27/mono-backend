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
    with _connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            amount   INTEGER NOT NULL,
            status   TEXT NOT NULL,
            claimed  INTEGER NOT NULL DEFAULT 0
        );
        """)
        conn.commit()


def upsert_order(order_id: str, amount: int, status: str) -> None:
    with _connect() as conn:
        conn.execute("""
        INSERT INTO orders (order_id, amount, status, claimed)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(order_id) DO UPDATE SET
            amount=excluded.amount,
            status=excluded.status;
        """, (order_id, amount, status))
        conn.commit()


def set_paid(order_id: str, amount: Optional[int] = None) -> None:
    with _connect() as conn:
        if amount is None:
            conn.execute("UPDATE orders SET status='paid' WHERE order_id=?;", (order_id,))
        else:
            conn.execute("UPDATE orders SET status='paid', amount=? WHERE order_id=?;", (int(amount), order_id))
        conn.commit()


def get_order(order_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT order_id, amount, status, claimed FROM orders WHERE order_id=?;",
            (order_id,)
        ).fetchone()
        return dict(row) if row else None


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

