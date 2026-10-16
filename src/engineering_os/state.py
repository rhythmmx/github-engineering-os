"""Transactional task leases survive worker interruption; SQLite is local state."""

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

    def report(self):
        return [
            dict(zip(("id", "status", "attempts", "lease_until", "detail"), r))
            for r in self.db.execute(
                "SELECT id,status,attempts,lease_until,detail FROM tasks ORDER BY id"
            )
        ]

    def close(self):
        self.db.close()
