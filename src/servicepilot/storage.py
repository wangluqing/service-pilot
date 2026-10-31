import csv
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[2]
ORDERS = BASE / "data" / "orders.csv"

def find_order(order_id: str) -> dict | None:
    with ORDERS.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["order_id"] == order_id:
                return row
    return None

def init_db(path: str) -> None:
    db = Path(path); db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL, analysis_json TEXT NOT NULL,
            confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL)""")

def save_ticket(path: str, message: str, analysis_json: str, confirmed_by: str) -> int:
    init_db(path)
    with sqlite3.connect(path) as conn:
        cur = conn.execute("INSERT INTO tickets(message, analysis_json, confirmed_by, created_at) VALUES (?,?,?,?)",
                           (message, analysis_json, confirmed_by, datetime.now(timezone.utc).isoformat()))
        return int(cur.lastrowid)

def list_tickets(path: str) -> list[dict]:
    init_db(path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 100")]
