from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      action TEXT NOT NULL,
      confidence REAL NOT NULL,
      reason TEXT NOT NULL,
      features_json TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      exchange_order_id TEXT,
      symbol TEXT NOT NULL,
      side TEXT NOT NULL,
      quantity REAL NOT NULL,
      price REAL NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fills (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      order_id INTEGER NOT NULL,
      fill_price REAL NOT NULL,
      fill_quantity REAL NOT NULL,
      fee REAL NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY(order_id) REFERENCES orders(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      symbol TEXT NOT NULL,
      side TEXT NOT NULL,
      quantity REAL NOT NULL,
      avg_entry REAL NOT NULL,
      status TEXT NOT NULL,
      closed_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL,
      details TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_commands (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      command_type TEXT NOT NULL,
      issued_by TEXT NOT NULL,
      params_json TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS pnl_snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      equity REAL NOT NULL,
      day_pnl_pct REAL NOT NULL,
      created_at TEXT NOT NULL
    );
    """,
]


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connect() as conn:
            for stmt in SCHEMA_STATEMENTS:
                conn.execute(stmt)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_signal(
        self,
        symbol: str,
        action: str,
        confidence: float,
        reason: str,
        features: dict,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals(symbol, action, confidence, reason, features_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (symbol, action, confidence, reason, json.dumps(features), self._now()),
            )
            return int(cur.lastrowid)

    def save_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        status: str,
        exchange_order_id: str | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO orders(exchange_order_id, symbol, side, quantity, price, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (exchange_order_id, symbol, side, quantity, price, status, self._now()),
            )
            return int(cur.lastrowid)

    def save_fill(self, order_id: int, fill_price: float, fill_quantity: float, fee: float) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO fills(order_id, fill_price, fill_quantity, fee, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, fill_price, fill_quantity, fee, self._now()),
            )
            return int(cur.lastrowid)

    def save_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        avg_entry: float,
        status: str = "OPEN",
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO positions(symbol, side, quantity, avg_entry, status, closed_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (symbol, side, quantity, avg_entry, status),
            )
            return int(cur.lastrowid)

    def close_position(self, position_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE positions SET status='CLOSED', closed_at=? WHERE id=?",
                (self._now(), position_id),
            )

    def count_open_positions(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM positions WHERE status='OPEN'").fetchone()
            return int(row["c"])

    def save_risk_event(self, event_type: str, details: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO risk_events(event_type, details, created_at) VALUES (?, ?, ?)",
                (event_type, details, self._now()),
            )
            return int(cur.lastrowid)

    def save_command(self, command_type: str, issued_by: str, params: dict) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_commands(command_type, issued_by, params_json, created_at) VALUES (?, ?, ?, ?)",
                (command_type, issued_by, json.dumps(params), self._now()),
            )
            return int(cur.lastrowid)

    def save_pnl_snapshot(self, equity: float, day_pnl_pct: float) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO pnl_snapshots(equity, day_pnl_pct, created_at) VALUES (?, ?, ?)",
                (equity, day_pnl_pct, self._now()),
            )
            return int(cur.lastrowid)

    def last_closed_trade_time(self) -> datetime | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT closed_at FROM positions WHERE status='CLOSED' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row or row["closed_at"] is None:
                return None
            return datetime.fromisoformat(row["closed_at"])
