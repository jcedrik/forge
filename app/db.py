"""Tiny persistence layer: one table of request metadata.

Postgres on RDS in AWS (DATABASE_URL from Secrets Manager via the task
definition), SQLite in tests and in `make demo` so nothing needs a network.
Only metadata is stored: request id, client id, timestamp, outcome, latency.
Never the prompt, never the response. That is a deliberate data-minimisation
choice and it is what lets the service claim "no PII at rest".
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager

_DDL = """
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    client_id  TEXT NOT NULL,
    ts         TEXT NOT NULL,
    outcome    TEXT NOT NULL,
    latency_ms INTEGER NOT NULL
)
"""


class Store:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ.get("DATABASE_URL", "sqlite:///./forge.db")
        if self.url.startswith("postgresql://") or self.url.startswith("postgres://"):
            import psycopg  # type: ignore  # only needed in AWS

            self._connect = lambda: psycopg.connect(self.url)
            self._param = "%s"
        else:
            path = self.url.replace("sqlite:///", "")
            self._connect = lambda: sqlite3.connect(path)
            self._param = "?"
        with self._conn() as c:
            c.execute(_DDL)

    @contextmanager
    def _conn(self):
        c = self._connect()
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def record(self, request_id: str, client_id: str, outcome: str, latency_ms: int) -> None:
        p = self._param
        with self._conn() as c:
            c.execute(
                f"INSERT INTO requests (request_id, client_id, ts, outcome, latency_ms) VALUES ({p}, {p}, {p}, {p}, {p})",
                (request_id, client_id, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), outcome, latency_ms),
            )

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM requests").fetchone()[0]

    def ping(self) -> bool:
        try:
            with self._conn() as c:
                c.execute("SELECT 1")
            return True
        except Exception:
            return False
