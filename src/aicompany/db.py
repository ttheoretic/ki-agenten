"""SQLite-Persistenz für Aufgaben, Ereignisse, Kosten, Freigaben, Kennzahlen und Steuerzustand.

Jeder Zugriff öffnet eine eigene Verbindung (WAL-Modus), damit Server, CLI und Scheduler
parallel auf dieselbe Datenbank zugreifen können. Atomare Zustandswechsel laufen über
`BEGIN IMMEDIATE` bzw. bedingte UPDATEs (`... WHERE status = ?`).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  agent TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  goal TEXT NOT NULL,
  description TEXT NOT NULL,
  phase INTEGER NOT NULL,
  cycle INTEGER NOT NULL DEFAULT 1,
  inputs TEXT NOT NULL DEFAULT '{}',
  depends_on TEXT NOT NULL DEFAULT '[]',
  output_format TEXT NOT NULL,
  acceptance TEXT NOT NULL DEFAULT '[]',
  priority INTEGER NOT NULL DEFAULT 50,
  status TEXT NOT NULL DEFAULT 'pending',
  review_by TEXT,
  not_before_day INTEGER NOT NULL DEFAULT 1,
  revision_count INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  est_cost_eur REAL NOT NULL DEFAULT 0,
  actual_cost_eur REAL NOT NULL DEFAULT 0,
  result TEXT,
  artifacts TEXT NOT NULL DEFAULT '[]',
  history TEXT NOT NULL DEFAULT '[]',
  feedback TEXT NOT NULL DEFAULT '[]',
  error TEXT,
  claimed_by TEXT,
  created_by TEXT NOT NULL DEFAULT 'system',
  parent_task_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent ON tasks(agent);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'info',
  agent TEXT,
  from_agent TEXT,
  to_agent TEXT,
  task_id TEXT,
  run_id TEXT,
  approval_id TEXT,
  message TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  mode TEXT NOT NULL,
  trigger TEXT NOT NULL,
  experiment_day INTEGER,
  agent_calls INTEGER NOT NULL DEFAULT 0,
  cost_eur REAL NOT NULL DEFAULT 0,
  stop_reason TEXT,
  heartbeat_at TEXT NOT NULL,
  pid INTEGER
);

CREATE TABLE IF NOT EXISTS cost_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  month TEXT NOT NULL,
  run_id TEXT,
  task_id TEXT,
  agent TEXT,
  model TEXT,
  kind TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  cost_eur REAL NOT NULL,
  estimated INTEGER NOT NULL DEFAULT 0,
  simulated INTEGER NOT NULL DEFAULT 0,
  note TEXT
);

CREATE TABLE IF NOT EXISTS budget_alerts (
  month TEXT NOT NULL, scope TEXT NOT NULL, threshold REAL NOT NULL, ts TEXT NOT NULL,
  PRIMARY KEY (month, scope, threshold)
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  idem_key TEXT UNIQUE NOT NULL,
  task_id TEXT,
  agent TEXT NOT NULL,
  action_type TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  justification TEXT NOT NULL,
  expected_benefit TEXT NOT NULL,
  params TEXT NOT NULL,
  params_hash TEXT NOT NULL,
  cost_eur REAL NOT NULL DEFAULT 0,
  recurring_cost_eur REAL NOT NULL DEFAULT 0,
  budget_impact TEXT NOT NULL DEFAULT '{}',
  risks TEXT NOT NULL DEFAULT '[]',
  alternatives TEXT NOT NULL DEFAULT '[]',
  planned_at TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  decided_at TEXT,
  decided_by TEXT,
  decision_note TEXT,
  execution_status TEXT NOT NULL DEFAULT 'not_started',
  execution_result TEXT,
  executed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT, details TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS control (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_control (agent TEXT PRIMARY KEY, paused INTEGER NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL, note TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, agent TEXT NOT NULL, task_id TEXT, kind TEXT NOT NULL,
  summary TEXT NOT NULL, rationale TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ideas (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, score REAL, status TEXT NOT NULL DEFAULT 'candidate',
  data TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  path TEXT PRIMARY KEY, task_id TEXT, agent TEXT, kind TEXT, sha256 TEXT, size INTEGER, created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def month_key(ts: datetime | None = None) -> str:
    return (ts or datetime.now(timezone.utc)).strftime("%Y-%m")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
            if "cycle" not in cols:  # Migration älterer Datenbanken
                conn.execute("ALTER TABLE tasks ADD COLUMN cycle INTEGER NOT NULL DEFAULT 1")
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self.connect() as conn:
            return conn.execute(sql, params)

    # Key/Value-Hilfen
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM meta WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def audit(self, actor: str, action: str, target: str | None, details: dict | None = None) -> None:
        self.execute(
            "INSERT INTO audit_log(ts, actor, action, target, details) VALUES (?,?,?,?,?)",
            (now_iso(), actor, action, target, dumps(details or {})),
        )
