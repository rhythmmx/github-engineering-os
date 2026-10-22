"""Transactional task leases survive worker interruption; SQLite is local state."""

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

STATUSES = {
    "discovered",
    "planned",
    "building",
    "testing",
    "ready_for_review",
    "published",
    "needs_repair",
}
PROMOTION_FILES = frozenset(
    {
        "health.py",
        "spec.json",
        "README.md",
        "cli.py",
        "test_health.py",
        "validation.json",
    }
)


def _validate_inventory(inventory):
    if not isinstance(inventory, dict) or set(inventory) != PROMOTION_FILES:
        raise ValueError("Invalid promotion inventory")
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
        for value in inventory.values()
    ):
        raise ValueError("Invalid promotion inventory")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.leases: dict[str, str] = {}
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
          lease_until REAL NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, task TEXT NOT NULL, at REAL NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS promotions (
          task_id TEXT PRIMARY KEY, destination TEXT NOT NULL, inventory TEXT NOT NULL);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(tasks)")}
        if "lease_owner" not in columns:
            self.db.execute("ALTER TABLE tasks ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
            self.db.commit()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def seed(self, task_id: str):
        with self.transaction():
            self.db.execute(
                "INSERT OR IGNORE INTO tasks(id,status) VALUES (?, 'planned')", (task_id,)
            )

    def claim(self, task_id: str, max_attempts: int = 3, lease_seconds: int = 900) -> bool:
        with self.transaction():
            row = self.db.execute(
                "SELECT status,attempts,lease_until FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row or row[0] in {"ready_for_review", "published"}:
                return False
            if row[2] > time.time():
                return False
            if row[1] >= max_attempts:
                self.db.execute(
                    "UPDATE tasks SET status='needs_repair',lease_until=0,"
                    "detail='retry_budget_exhausted' WHERE id=?",
                    (task_id,),
                )
                return False
            owner = uuid.uuid4().hex
            self.db.execute(
                "UPDATE tasks SET status='building',attempts=attempts+1,lease_until=?,"
                "lease_owner=? WHERE id=?",
                (time.time() + lease_seconds, owner, task_id),
            )
            self.leases[task_id] = owner
            return True

    def finish(self, task_id: str, status: str, detail: str):
        if status not in STATUSES:
            raise ValueError("Unknown status")
        with self.transaction():
            changed = self.db.execute(
                "UPDATE tasks SET status=?,lease_until=0,detail=?,lease_owner='' "
                "WHERE id=? AND lease_owner=? AND lease_until>?",
                (status, detail, task_id, self.leases.get(task_id, "no-lease"), time.time()),
            ).rowcount
            if not changed:
                raise ValueError("Task lease expired or belongs to another worker")
            self.db.execute(
                "INSERT INTO events(task,at,detail) VALUES (?,?,?)", (task_id, time.time(), detail)
            )

    def prepare_promotion(self, task_id: str, destination: Path, inventory: dict[str, str]) -> None:
        """Journal validated staged bytes while this worker owns an active build."""
        _validate_inventory(inventory)
        try:
            target = str(destination.resolve())
        except (OSError, ValueError, RuntimeError):
            raise ValueError("Invalid promotion destination") from None
        with self.transaction():
            row = self.db.execute(
                "SELECT 1 FROM tasks WHERE id=? AND status='building' "
                "AND lease_owner=? AND lease_until>?",
                (task_id, self.leases.get(task_id, "no-lease"), time.time()),
            ).fetchone()
            if task_id not in self.leases or row is None:
                raise ValueError("Task lease expired or belongs to another worker")
            self.db.execute(
                "INSERT INTO promotions(task_id,destination,inventory) VALUES (?,?,?) "
                "ON CONFLICT(task_id) DO UPDATE SET destination=excluded.destination, "
                "inventory=excluded.inventory",
                (task_id, target, json.dumps(inventory, sort_keys=True)),
            )

    def load_promotion(self, task_id: str) -> dict | None:
        """Return a validated recovery receipt; receipt data is never a report field."""
        row = self.db.execute(
            "SELECT destination,inventory FROM promotions WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None

        def unique_pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Invalid promotion receipt")
                result[key] = value
            return result

        try:
            destination, encoded = row
            if not isinstance(destination, str) or not destination or len(destination) > 32_768:
                raise ValueError("Invalid promotion receipt")
            target = Path(destination)
            if not target.is_absolute() or str(target.resolve()) != destination:
                raise ValueError("Invalid promotion receipt")
            if not isinstance(encoded, str) or len(encoded) > 4096:
                raise ValueError("Invalid promotion receipt")
            inventory = json.loads(encoded, object_pairs_hook=unique_pairs)
            _validate_inventory(inventory)
        except (ValueError, TypeError, OSError, RuntimeError, RecursionError):
            raise ValueError("Invalid promotion receipt") from None
        return {"destination": destination, "inventory": inventory}

    def report(self):
        return [
            dict(zip(("id", "status", "attempts", "lease_until", "detail"), r))
            for r in self.db.execute(
                "SELECT id,status,attempts,lease_until,detail FROM tasks ORDER BY id"
            )
        ]

    def close(self):
        self.db.close()
