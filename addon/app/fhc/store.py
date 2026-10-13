import json
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, directory: Path, days: int = 7, limit: int = 1000):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "fhc.sqlite", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL NOT NULL, result TEXT NOT NULL
            );
            PRAGMA user_version=1;
        """)
        self.days, self.limit = days, limit
        for request_id, raw in self.db.execute("SELECT id, result FROM requests").fetchall():
            result = json.loads(raw)
            if result["status"] in {"accepted", "planning", "executing"}:
                result.update(status="uncertain", reason="restart_interrupted")
                self.save(request_id, result)

    def policy(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()
        return json.loads(row[0]) if row else {"light": True, "switch": True}

    def set_policy(self, policy):
        self.db.execute(
            "INSERT OR REPLACE INTO settings VALUES ('policy', ?)", (json.dumps(policy),)
        )
        self.db.commit()

    def get(self, request_id):
        row = self.db.execute(
            "SELECT text, result FROM requests WHERE id=?", (request_id,)
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def insert(self, request_id, text):
        self.prune()
        result = {
            "id": request_id,
            "text": text,
            "status": "accepted",
            "actions": [],
            "timings_ms": {},
            "created": time.time(),
            "reason": None,
        }
        self.db.execute(
            "INSERT INTO requests VALUES (?, ?, ?, ?)",
            (request_id, text, result["created"], json.dumps(result)),
        )
        self.db.commit()
        return result

    def save(self, request_id, result):
        self.db.execute(
            "UPDATE requests SET result=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), request_id),
        )
        self.db.commit()

    def recent(self):
        self.prune()
        rows = self.db.execute(
            "SELECT result FROM requests ORDER BY created DESC LIMIT 50"
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def prune(self):
        # Keep at least 24 hours of request IDs, independently of the visible history limit.
        cutoff = time.time() - self.days * 86400
        self.db.execute("DELETE FROM requests WHERE created < ?", (cutoff,))
        self.db.execute(
            """DELETE FROM requests WHERE created < ? AND id NOT IN
            (SELECT id FROM requests ORDER BY created DESC LIMIT ?)""",
            (time.time() - 86400, self.limit),
        )
        self.db.commit()

    def clear_history(self):
        # Preserve IDs and execution status for deduplication, remove command content.
        for request_id, raw in self.db.execute("SELECT id, result FROM requests").fetchall():
            result = json.loads(raw)
            result.update(text="", actions=[], hidden=True)
            self.db.execute(
                "UPDATE requests SET text='', result=? WHERE id=?", (json.dumps(result), request_id)
            )
        self.db.commit()

    def close(self):
        self.db.close()
