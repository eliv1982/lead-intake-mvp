"""Compact API test suite for lead-intake-mvp.

Uses only the standard library `unittest` plus FastAPI's TestClient, as the
project does not need a heavier test stack. See `tests/__init__.py` for how
the SQLite DB and event log are redirected to a temporary location so this
suite never touches the repository's real `data/leads.db` or
`logs/events.log`.
"""

import sqlite3
import uuid
from unittest.mock import patch

# `tests.base` must be imported before anything under `app.*` - importing
# the `tests` package first is what redirects the DB/log paths away from
# the repository's real files (see tests/__init__.py).
from tests.base import ApiTestCase

from fastapi import HTTPException

import app.main as main
from app.models import (
    COMMENT_MAX_LENGTH,
    CONTACT_MAX_LENGTH,
    NAME_MAX_LENGTH,
    SOURCE_MAX_LENGTH,
)


def unique_contact(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}@example.com"


class HealthTests(ApiTestCase):
    def test_health_returns_documented_ok_response(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ValidLeadTests(ApiTestCase):
    def test_minimal_payload_is_accepted_and_persisted(self) -> None:
        contact = unique_contact("minimal")
        response = self.client.post("/lead", json={"contact": contact})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body["id"], int)
        self.assertEqual(body["message"], "Lead saved successfully.")

        row = self.fetch_lead(body["id"])
        self.assertIsNotNone(row)
        self.assertEqual(row["contact"], contact)
        self.assertIsNone(row["name"])
        self.assertIsNone(row["source"])
        self.assertIsNone(row["comment"])

    def test_full_payload_persists_all_fields(self) -> None:
        contact = unique_contact("full")
        payload = {
            "name": "Jane Doe",
            "contact": contact,
            "source": "landing-page",
            "comment": "Interested in pricing.",
        }
        response = self.client.post("/lead", json=payload)

        self.assertEqual(response.status_code, 200)
        lead_id = response.json()["id"]

        row = self.fetch_lead(lead_id)
        self.assertEqual(row["name"], "Jane Doe")
        self.assertEqual(row["contact"], contact)
        self.assertEqual(row["source"], "landing-page")
        self.assertEqual(row["comment"], "Interested in pricing.")

    def test_contact_is_trimmed_before_storage(self) -> None:
        raw_contact = f"  padded-{uuid.uuid4()}@example.com  "
        response = self.client.post("/lead", json={"contact": raw_contact})

        self.assertEqual(response.status_code, 200)
        lead_id = response.json()["id"]
        row = self.fetch_lead(lead_id)
        self.assertEqual(row["contact"], raw_contact.strip())

    def test_successful_lead_produces_one_diagnostic_event(self) -> None:
        contact = unique_contact("event")
        response = self.client.post("/lead", json={"contact": contact})

        self.assertEqual(response.status_code, 200)
        lead_id = response.json()["id"]

        log_text = self.read_log_text()
        self.assertIn(f"New lead saved: {lead_id}", log_text)


class ValidationTests(ApiTestCase):
    def assert_validation_rejected(self, response) -> None:
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("detail", body)
        self.assertIsInstance(body["detail"], str)

    def test_missing_body_is_rejected(self) -> None:
        response = self.client.post("/lead")
        self.assert_validation_rejected(response)

    def test_malformed_json_is_rejected(self) -> None:
        response = self.client.post(
            "/lead",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        self.assert_validation_rejected(response)

    def test_json_null_body_is_rejected(self) -> None:
        response = self.client.post(
            "/lead", content=b"null", headers={"Content-Type": "application/json"}
        )
        self.assert_validation_rejected(response)

    def test_list_body_is_rejected(self) -> None:
        response = self.client.post(
            "/lead", content=b"[1, 2, 3]", headers={"Content-Type": "application/json"}
        )
        self.assert_validation_rejected(response)

    def test_scalar_body_is_rejected(self) -> None:
        response = self.client.post(
            "/lead", content=b"42", headers={"Content-Type": "application/json"}
        )
        self.assert_validation_rejected(response)

    def test_missing_contact_is_rejected(self) -> None:
        response = self.client.post("/lead", json={"name": "No Contact"})
        self.assert_validation_rejected(response)

    def test_null_contact_is_rejected(self) -> None:
        response = self.client.post("/lead", json={"contact": None})
        self.assert_validation_rejected(response)

    def test_wrong_contact_type_is_rejected(self) -> None:
        response = self.client.post("/lead", json={"contact": 12345})
        self.assert_validation_rejected(response)

    def test_whitespace_only_contact_is_rejected(self) -> None:
        response = self.client.post("/lead", json={"contact": "   "})
        self.assert_validation_rejected(response)

    def test_wrong_optional_field_type_is_rejected(self) -> None:
        response = self.client.post(
            "/lead", json={"contact": unique_contact("badname"), "name": 12345}
        )
        self.assert_validation_rejected(response)

    def test_oversized_contact_is_rejected(self) -> None:
        response = self.client.post(
            "/lead", json={"contact": "a" * (CONTACT_MAX_LENGTH + 1)}
        )
        self.assert_validation_rejected(response)

    def test_oversized_name_is_rejected(self) -> None:
        response = self.client.post(
            "/lead",
            json={
                "contact": unique_contact("oversized-name"),
                "name": "a" * (NAME_MAX_LENGTH + 1),
            },
        )
        self.assert_validation_rejected(response)

    def test_oversized_source_is_rejected(self) -> None:
        response = self.client.post(
            "/lead",
            json={
                "contact": unique_contact("oversized-source"),
                "source": "a" * (SOURCE_MAX_LENGTH + 1),
            },
        )
        self.assert_validation_rejected(response)

    def test_oversized_comment_is_rejected(self) -> None:
        response = self.client.post(
            "/lead",
            json={
                "contact": unique_contact("oversized-comment"),
                "comment": "a" * (COMMENT_MAX_LENGTH + 1),
            },
        )
        self.assert_validation_rejected(response)


class DuplicateLeadTests(ApiTestCase):
    def test_duplicate_contact_submissions_are_allowed_with_distinct_ids(self) -> None:
        """The project deliberately does not deduplicate or enforce
        uniqueness on `contact`. This test proves and locks in that
        behavior; it must keep passing unless that design is intentionally
        revisited."""
        contact = unique_contact("dup")

        first = self.client.post("/lead", json={"contact": contact})
        second = self.client.post("/lead", json={"contact": contact})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        first_id = first.json()["id"]
        second_id = second.json()["id"]
        self.assertNotEqual(first_id, second_id)

        rows = self.fetch_leads_by_contact(contact)
        self.assertEqual(len(rows), 2)


class PersistenceFailureTests(ApiTestCase):
    def test_expected_sqlite_error_returns_generic_json_500(self) -> None:
        with patch.object(
            main, "get_connection", side_effect=sqlite3.OperationalError("disk I/O error")
        ):
            response = self.client.post("/lead", json={"contact": unique_contact("dberr")})

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body, {"detail": "Database error."})

    def test_unexpected_exception_returns_generic_json_500(self) -> None:
        before = self.count_leads()

        with patch.object(main, "get_connection", side_effect=RuntimeError("boom")):
            response = self.client.post(
                "/lead", json={"contact": unique_contact("unexpected")}
            )

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body, {"detail": "Internal server error."})
        self.assertNotIn("boom", str(body))
        self.assertNotIn("RuntimeError", str(body))

        # Nothing should have been persisted: the exception happened before
        # any insert was attempted.
        self.assertEqual(self.count_leads(), before)


class EventLoggingTests(ApiTestCase):
    def test_diagnostic_log_failure_does_not_roll_back_committed_lead(self) -> None:
        """Event logging is best-effort, not part of the DB transaction.

        If the diagnostic log write fails *after* the DB commit, the client
        gets a generic 500 (via the catch-all handler), but the lead row
        that was already committed remains in the database. This is
        documented, accepted behavior - not an audit guarantee.
        """
        contact = unique_contact("logfail")
        before = self.count_leads()

        with patch.object(main.event_logger, "info", side_effect=RuntimeError("log boom")):
            response = self.client.post("/lead", json={"contact": contact})

        self.assertEqual(response.status_code, 500)
        # Chosen, documented behavior (see README "Принятые ограничения
        # MVP"): a post-commit logging failure still surfaces as the same
        # generic catch-all 500 body as any other unexpected exception -
        # it is not special-cased into a 200, and it does not leak the
        # logging failure's own exception text.
        self.assertEqual(response.json(), {"detail": "Internal server error."})
        self.assertEqual(self.count_leads(), before + 1)

        rows = self.fetch_leads_by_contact(contact)
        self.assertEqual(len(rows), 1)

    def test_connection_is_closed_after_post_commit_logging_exception(self) -> None:
        """Direct proof that `create_lead`'s outer `finally: connection.close()`
        (app/main.py) actually runs on this path, not just that the
        temporary DB file eventually becomes removable (see
        tests/test_cleanup.py for that end-to-end, real-subprocess proof).

        Wraps `get_connection` to capture the real `sqlite3.Connection` it
        returns, then - after the request - tries to use that same
        connection object directly. A closed SQLite connection raises
        `ProgrammingError` on any further use, so this fails if the
        connection was left open (e.g. relying on GC/refcounting instead of
        an explicit `.close()`).
        """
        contact = unique_contact("connclose")
        captured: list = []
        real_get_connection = main.get_connection

        def spying_get_connection():
            connection = real_get_connection()
            captured.append(connection)
            return connection

        with patch.object(main, "get_connection", side_effect=spying_get_connection):
            with patch.object(
                main.event_logger, "info", side_effect=RuntimeError("log boom")
            ):
                response = self.client.post("/lead", json={"contact": contact})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(captured), 1)

        with self.assertRaises(sqlite3.ProgrammingError):
            captured[0].execute("SELECT 1")


class HandlerPrecedenceTests(ApiTestCase):
    """Proves the generic catch-all (app.main.catch_unhandled_exceptions)
    only ever intercepts exceptions that have no more specific handler, and
    never shadows FastAPI/Starlette's own HTTP-level responses (404, 405,
    or an explicitly raised HTTPException)."""

    def test_unknown_path_returns_404(self) -> None:
        response = self.client.get("/this-path-does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_unsupported_method_on_lead_returns_405(self) -> None:
        response = self.client.get("/lead")
        self.assertEqual(response.status_code, 405)

    def test_unsupported_method_on_health_returns_405(self) -> None:
        response = self.client.post("/health")
        self.assertEqual(response.status_code, 405)

    def test_raised_http_exception_is_not_converted_to_generic_500(self) -> None:
        """An HTTPException raised anywhere in a route must reach the
        client exactly as Starlette's own HTTPException handler renders
        it, never reshaped by the generic catch-all into its own
        "Internal server error." body."""
        with patch.object(
            main,
            "get_connection",
            side_effect=HTTPException(status_code=418, detail="teapot"),
        ):
            response = self.client.post(
                "/lead", json={"contact": unique_contact("teapot")}
            )

        self.assertEqual(response.status_code, 418)
        self.assertEqual(response.json(), {"detail": "teapot"})

    def test_expected_sqlite_error_keeps_its_own_message(self) -> None:
        """Companion to PersistenceFailureTests: the sqlite-specific 500
        keeps its own "Database error." message rather than being
        overwritten by the generic catch-all's "Internal server error.".
        """
        with patch.object(
            main, "get_connection", side_effect=sqlite3.OperationalError("locked")
        ):
            response = self.client.post(
                "/lead", json={"contact": unique_contact("precedence-db")}
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"detail": "Database error."})
