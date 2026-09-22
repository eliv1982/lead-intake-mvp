"""Shared test scaffolding.

Every test in this suite goes through the single isolated TestClient
defined here, backed by the temporary DB/log paths configured in
``tests/__init__.py``. Nothing in this file (or any test module) touches
the repository's real ``data/leads.db`` or ``logs/events.log``.
"""

import sqlite3
import unittest
from typing import Any, Optional

from fastapi.testclient import TestClient

from app.database import DB_PATH
from app.logger import LOG_PATH
from app.main import app


class ApiTestCase(unittest.TestCase):
    """Base test case: one started app (startup event has run) per class."""

    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        # raise_server_exceptions=False so that tests exercising the
        # generic-500 path get back the JSON response instead of the
        # underlying exception being re-raised into the test.
        cls.client = TestClient(app, raise_server_exceptions=False)
        cls.client.__enter__()  # runs the `startup` event -> init_db()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    # -- direct SQLite assertions (independent of the HTTP response) -----

    @staticmethod
    def fetch_lead(lead_id: int) -> Optional[sqlite3.Row]:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(
                "SELECT * FROM leads WHERE id = ?", (lead_id,)
            ).fetchone()
        finally:
            connection.close()

    @staticmethod
    def fetch_leads_by_contact(contact: str) -> list[sqlite3.Row]:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(
                "SELECT * FROM leads WHERE contact = ?", (contact,)
            ).fetchall()
        finally:
            connection.close()

    @staticmethod
    def count_leads() -> int:
        connection = sqlite3.connect(DB_PATH)
        try:
            return connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        finally:
            connection.close()

    @staticmethod
    def read_log_text() -> str:
        if not LOG_PATH.exists():
            return ""
        return LOG_PATH.read_text(encoding="utf-8")

    @staticmethod
    def valid_payload(**overrides: Any) -> dict:
        payload = {"contact": "lead@example.com"}
        payload.update(overrides)
        return payload
