import json
import sqlite3
import time
from pathlib import Path


class PolicyDict(dict):
    @property
    def domains(self) -> dict[str, bool]:
        return self.get("domains", {})

    @property
    def entities(self) -> dict[str, dict]:
        return self.get("entities", {})

    def is_domain_allowed(self, domain: str) -> bool:
        return bool(self.domains.get(domain, False))

    def is_allowed(self, domain: str, entity_id: str | None = None, identity=None) -> bool:
        if not self.is_domain_allowed(domain):
            return False
        if entity_id and entity_id in self.entities:
            entry = self.entities[entity_id]
            if entry.get("identity") and entry["identity"] != identity:
                return False  # Reused ID is quarantined until reconciliation/admin decision.
            return entry.get("enabled", True)
        return True

    def get(self, key, default=None):
        if key in self:
            return super().get(key, default)
        return self.domains.get(key, default)


class Store:
    def __init__(self, directory: Path, days: int = 7, limit: int = 1000):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "fhc.sqlite", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        self.days, self.limit = days, limit
        for request_id, raw in self.db.execute("SELECT id, result FROM requests").fetchall():
            result = json.loads(raw)
            if result["status"] in {"accepted", "planning", "executing"}:
                result.update(status="uncertain", reason="restart_interrupted")
                self.save(request_id, result)

    def _migrate(self):
        ver = self.db.execute("PRAGMA user_version").fetchone()[0]
        if ver > 3:
            self.db.close()
            raise ValueError("unsupported_database_version")
        existing = self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone()
        try:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL NOT NULL, result TEXT NOT NULL)"
                )
                row = self.db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()
                if row:
                    raw = json.loads(row[0])
                    if not isinstance(raw, dict):
                        raise ValueError("invalid_policy")
                    if "domains" not in raw:
                        raw = {"domains": {**raw, "climate": False}, "entities": {}}
                else:
                    raw = {
                        "domains": {"light": True, "switch": True, "climate": not bool(existing)},
                        "entities": {},
                    }
                self._validate_policy(raw)
                raw.setdefault("revision", 0)
                self.db.execute(
                    "INSERT OR REPLACE INTO settings VALUES ('policy', ?)", (json.dumps(raw),)
                )
                self.db.execute("PRAGMA user_version=3")
        except Exception:
            self.db.close()
            raise ValueError("database_migration_failed") from None

    @staticmethod
    def _validate_policy(policy):
        if not isinstance(policy.get("domains"), dict) or not isinstance(
            policy.get("entities"), dict
        ):
            raise ValueError("invalid_policy")
        if any(type(v) is not bool for v in policy["domains"].values()):
            raise ValueError("invalid_policy")
        for entry in policy["entities"].values():
            if not isinstance(entry, dict) or type(entry.get("enabled")) is not bool:
                raise ValueError("invalid_policy")

    def policy(self) -> PolicyDict:
        row = self.db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()
        return PolicyDict(json.loads(row[0]))

    def set_policy(self, policy: dict):
        current = self.policy()
        if "domains" not in policy:
            policy = {"domains": policy, "entities": current.entities}
        self._validate_policy(policy)
        policy = {**policy, "revision": current.get("revision", 0) + 1}
        self.db.execute(
            "INSERT OR REPLACE INTO settings VALUES ('policy', ?)", (json.dumps(policy),)
        )
        self.db.commit()

    def set_entity_policy(self, entity_id: str, enabled: bool, identity=None):
        current = self.policy()
        entities = dict(current.entities)
        entities[entity_id] = {"enabled": enabled, "identity": identity}
        self.set_policy({"domains": current.domains, "entities": entities})

    def reconcile_registry(self, ha):
        current = self.policy()
        entities = dict(current.entities)
        by_identity = {r["id"]: r["entity_id"] for r in ha.registry if r.get("id")}
        registry = {r["entity_id"]: r for r in ha.registry}
        for old, entry in list(current.entities.items()):
            identity = entry.get("identity")
            new = (
                by_identity.get(identity) if identity else getattr(ha, "renames", {}).get(old, old)
            )
            if new and new != old:
                # Never silently merge two conflicting overrides.
                if new in entities and entities[new] != entry:
                    entities[new] = {"enabled": False, "identity": identity}
                else:
                    entities[new] = dict(entry)
                del entities[old]
            if new in entities and not identity and registry.get(new, {}).get("id"):
                entities[new] = {**entities[new], "identity": registry[new]["id"]}
        if entities != current.entities:
            self.set_policy({"domains": current.domains, "entities": entities})

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

    def recent_shortcuts(self, limit: int = 6) -> list[str]:
        self.prune()
        rows = self.db.execute(
            "SELECT text, result FROM requests WHERE text != '' ORDER BY created DESC"
        ).fetchall()
        shortcuts = []
        seen = set()
        for text, raw in rows:
            try:
                res = json.loads(raw)
                if res.get("status") == "succeeded" and not res.get("hidden"):
                    norm = " ".join(text.split())
                    if norm and norm not in seen:
                        seen.add(norm)
                        shortcuts.append(norm)
                        if len(shortcuts) >= limit:
                            break
            except Exception:
                continue
        return shortcuts

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
