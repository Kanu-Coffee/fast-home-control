import json
import sqlite3
import time
from pathlib import Path

# Presence/schedule domains are never read-allowed by default; they need explicit opt-in.
PERSONAL_READ_DOMAINS = frozenset({"person", "device_tracker", "zone", "calendar", "todo"})
DEFAULT_READ_DOMAINS = (
    frozenset({"sensor", "binary_sensor", "weather", "event", "sun", "update"})
    - PERSONAL_READ_DOMAINS
)


class PolicyDict(dict):
    @property
    def domains(self):
        return self.get("domains") or {}

    @property
    def read_domains(self):
        return self.get("read_domains") or {}

    @property
    def entities(self):
        return self.get("entities") or {}

    def is_domain_allowed(self, domain: str, access: str = "write") -> bool:
        if access == "read":
            if domain in self.read_domains:
                return bool(self.read_domains[domain])
            if domain in self.domains:
                return bool(self.domains[domain])
            if domain in PERSONAL_READ_DOMAINS:
                return False  # explicit opt-in only; never auto-expanded by updates
            if domain in DEFAULT_READ_DOMAINS:
                return True
            return False
        return bool(self.domains.get(domain, False))

    def is_allowed(
        self,
        domain: str,
        entity_id: str | None = None,
        identity=None,
        access: str = "write",
    ) -> bool:
        if not self.is_domain_allowed(domain, access=access):
            return False
        if entity_id and entity_id in self.entities:
            entry = self.entities[entity_id]
            if entry.get("identity") and entry["identity"] != identity:
                return False  # Reused ID is quarantined until reconciliation/admin decision.
            if access == "read":
                if "read_enabled" in entry:
                    return bool(entry["read_enabled"])
                return bool(entry.get("enabled", True))
            return bool(entry.get("enabled", True))
        return True

    def get(self, key, default=None):
        if key in self:
            return dict.get(self, key, default)
        return self.domains.get(key, default)


def as_policy_dict(policy) -> PolicyDict:
    """Normalize bare {domain: bool} mappings and plain dicts into one PolicyDict."""
    if isinstance(policy, PolicyDict):
        return policy
    raw = dict(policy)
    if {"domains", "read_domains", "entities"} & raw.keys():
        return PolicyDict(raw)
    domains = {k: v for k, v in raw.items() if isinstance(v, bool)}
    return PolicyDict({**raw, "domains": domains})


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
                raw: dict
                if row:
                    raw = json.loads(row[0])
                    if not isinstance(raw, dict):
                        raise ValueError("invalid_policy")
                    if "domains" not in raw:
                        raw = {"domains": {**raw, "climate": False}, "entities": {}}
                else:
                    raw = {
                        "domains": {"light": True, "switch": True, "climate": not bool(existing)},
                        "read_domains": {},
                        "entities": {},
                    }
                raw.setdefault("read_domains", {})
                self._validate_policy(raw)
                raw.setdefault("revision", 0)
                self.db.execute(
                    "INSERT OR REPLACE INTO settings VALUES ('policy', ?)", (json.dumps(raw),)
                )
                self.db.execute("PRAGMA user_version=3")
        except Exception:
            self.db.close()
            raise ValueError("database_migration_failed") from None

    POLICY_KEYS = frozenset({"domains", "read_domains", "entities", "revision"})
    ENTITY_KEYS = frozenset({"enabled", "read_enabled", "identity"})

    @staticmethod
    def _validate_bool_map(value):
        if not isinstance(value, dict) or any(
            not isinstance(k, str) or type(v) is not bool for k, v in value.items()
        ):
            raise ValueError("invalid_policy")

    @classmethod
    def _validate_policy(cls, policy):
        if not isinstance(policy, dict):
            raise ValueError("invalid_policy")
        unknown = set(policy) - cls.POLICY_KEYS
        if unknown:
            raise ValueError("invalid_policy")
        if not isinstance(policy.get("domains"), dict) or not isinstance(
            policy.get("entities"), dict
        ):
            raise ValueError("invalid_policy")
        cls._validate_bool_map(policy["domains"])
        cls._validate_bool_map(policy.get("read_domains") or {})
        revision = policy.get("revision", 0)
        if type(revision) is not int or revision < 0:
            raise ValueError("invalid_policy")
        for entry in policy["entities"].values():
            if not isinstance(entry, dict) or set(entry) - cls.ENTITY_KEYS:
                raise ValueError("invalid_policy")
            if type(entry.get("enabled")) is not bool:
                raise ValueError("invalid_policy")
            if "read_enabled" in entry and type(entry["read_enabled"]) is not bool:
                raise ValueError("invalid_policy")
            if "identity" in entry and not isinstance(entry["identity"], (str, type(None))):
                raise ValueError("invalid_policy")

    def policy(self) -> PolicyDict:
        row = self.db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()
        return PolicyDict(json.loads(row[0]))

    def set_policy(self, policy: dict):
        current = self.policy()
        if "domains" not in policy:
            policy = {"domains": policy, "entities": current.entities}
        # Partial writes must never silently drop unrelated sections.
        policy = dict(policy)
        policy.setdefault("read_domains", current.read_domains)
        policy.setdefault("entities", current.entities)
        self._validate_policy(policy)
        revision = current.get("revision", 0)
        policy["revision"] = (revision if isinstance(revision, int) else 0) + 1
        self.db.execute(
            "INSERT OR REPLACE INTO settings VALUES ('policy', ?)", (json.dumps(policy),)
        )
        self.db.commit()

    def set_entity_policy(self, entity_id: str, enabled: bool, identity=None, read_enabled=None):
        current = self.policy()
        entities = dict(current.entities)
        existing = entities.get(entity_id, {})
        entry = {**existing, "enabled": enabled}
        if read_enabled is not None:
            entry["read_enabled"] = read_enabled
        entry["identity"] = identity if identity is not None else existing.get("identity")
        entities[entity_id] = entry
        self.set_policy(
            {
                "domains": current.domains,
                "read_domains": current.read_domains,
                "entities": entities,
            }
        )

    def reconcile_registry(self, ha):
        current = self.policy()
        by_identity = {r["id"]: r["entity_id"] for r in ha.registry if r.get("id")}
        registry = {r["entity_id"]: r for r in ha.registry}
        renames = getattr(ha, "renames", {})

        new_entities = {}
        for old_id, entry in current.entities.items():
            identity = entry.get("identity")
            target_id = by_identity.get(identity) if identity else renames.get(old_id, old_id)
            if not target_id:
                target_id = old_id

            effective_identity = identity or registry.get(target_id, {}).get("id")
            new_entry = {
                "enabled": entry.get("enabled", True),
                "identity": effective_identity,
            }
            # Read settings survive rename/swap/cycle exactly like write settings.
            if "read_enabled" in entry:
                new_entry["read_enabled"] = bool(entry["read_enabled"])

            if target_id in new_entities:
                existing = new_entities[target_id]
                both_enabled = existing.get("enabled", True) and new_entry.get("enabled", True)
                merged = {
                    "enabled": both_enabled,
                    "identity": existing.get("identity") or new_entry.get("identity"),
                }
                if "read_enabled" in existing or "read_enabled" in new_entry:
                    merged["read_enabled"] = bool(existing.get("read_enabled", True)) and bool(
                        new_entry.get("read_enabled", True)
                    )
                new_entities[target_id] = merged
            else:
                new_entities[target_id] = new_entry

        if new_entities != current.entities:
            self.set_policy(
                {
                    "domains": current.domains,
                    "read_domains": current.read_domains,
                    "entities": new_entities,
                }
            )

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
                if res.get("status") != "succeeded" or res.get("hidden"):
                    continue
                # Exclude condition not met, pure queries, or text/message commands
                if res.get("reason") in {"condition_not_met", "query_succeeded"}:
                    continue
                if res.get("condition_result") is False or res.get("query_results"):
                    continue
                actions = res.get("actions", [])
                if not actions or all(a.get("is_query") for a in actions):
                    continue
                if any(a.get("domain") in {"input_text", "notify", "tts"} for a in actions):
                    continue
                # Must have at least one dispatched or already-in-state physical control action
                if not any(a.get("status") in {"sent", "already_in_state"} for a in actions):
                    continue

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
        # Preserve IDs and execution status for deduplication, strictly remove command content and plans.
        ALLOWED_FIELDS = {
            "id",
            "created",
            "status",
            "reason",
            "hidden",
            "timings_ms",
            "providers",
            "model_calls",
        }
        for request_id, raw in self.db.execute("SELECT id, result FROM requests").fetchall():
            try:
                res = json.loads(raw)
            except Exception:
                res = {}
            cleaned = {k: v for k, v in res.items() if k in ALLOWED_FIELDS}
            cleaned["text"] = ""
            cleaned["actions"] = []
            cleaned["hidden"] = True
            self.db.execute(
                "UPDATE requests SET text='', result=? WHERE id=?",
                (json.dumps(cleaned, ensure_ascii=False), request_id),
            )
        self.db.commit()

    def close(self):
        self.db.close()
