from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StoredResponse:
    request_hash: str
    status_code: int
    response_json: Dict[str, Any]


class IdempotencyStore:
    """Interface for storing idempotency results."""

    def get(self, key: str) -> Optional[StoredResponse]:
        raise NotImplementedError

    def put(self, key: str, request_hash: str, status_code: int, response_json: Dict[str, Any]) -> None:
        raise NotImplementedError


class MemoryStore(IdempotencyStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, StoredResponse] = {}

    def get(self, key: str) -> Optional[StoredResponse]:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, request_hash: str, status_code: int, response_json: Dict[str, Any]) -> None:
        with self._lock:
            self._data[key] = StoredResponse(
                request_hash=request_hash,
                status_code=status_code,
                response_json=response_json,
            )


class SQLiteStore(IdempotencyStore):
    """SQLite-backed store (single-process demo; not for multi-instance without proper locking)."""

    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                response_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[StoredResponse]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT request_hash, status_code, response_json FROM idempotency WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            request_hash, status_code, response_json = row
            return StoredResponse(
                request_hash=request_hash,
                status_code=int(status_code),
                response_json=json.loads(response_json),
            )

    def put(self, key: str, request_hash: str, status_code: int, response_json: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO idempotency(key, request_hash, status_code, response_json) VALUES (?, ?, ?, ?)",
                (key, request_hash, int(status_code), json.dumps(response_json, ensure_ascii=False)),
            )
            self._conn.commit()


def build_store() -> IdempotencyStore:
    """Choose a store via environment:
    - IDEMPOTENCY_STORE=memory (default)
    - IDEMPOTENCY_STORE=sqlite and IDEMPOTENCY_DB=./idempotency.sqlite3
    """
    store_kind = (os.getenv("IDEMPOTENCY_STORE") or "memory").strip().lower()
    if store_kind == "sqlite":
        db_path = os.getenv("IDEMPOTENCY_DB") or "./idempotency.sqlite3"
        return SQLiteStore(db_path=db_path)
    return MemoryStore()