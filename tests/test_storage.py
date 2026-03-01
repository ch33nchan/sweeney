from __future__ import annotations

from pathlib import Path
import unittest

from openclaw_bot.storage import SQLiteStore


class StorageTests(unittest.TestCase):
    def test_store_initializes_and_counts_positions(self) -> None:
        db = Path("/tmp/openclaw_bot_test.sqlite3")
        if db.exists():
            db.unlink()

        store = SQLiteStore(str(db))
        self.assertEqual(store.count_open_positions(), 0)
        store.save_position("BTC/USDT", "BUY", 0.01, 100.0)
        self.assertEqual(store.count_open_positions(), 1)

        if db.exists():
            db.unlink()


if __name__ == "__main__":
    unittest.main()
