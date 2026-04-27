import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.database import get_connection, init_db
from app.logger import get_event_logger
from app.models import LeadCreate


app = FastAPI(title="lead-intake-mvp")
event_logger = get_event_logger()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.exception_handler(RequestValidationError)
def handle_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    messages = []
    for item in error.errors():
        location = [str(part) for part in item.get("loc", []) if part != "body"]
        field = ".".join(location) if location else "request"
        message = item.get("msg", "Invalid value.")
        messages.append(f"{field}: {message}")

    detail = "; ".join(messages) if messages else "Invalid request payload."
    return JSONResponse(status_code=400, content={"detail": detail})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/lead")
def create_lead(lead: LeadCreate) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()

    try:
        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO leads (created_at, name, contact, source, comment)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_at, lead.name, lead.contact, lead.source, lead.comment),
            )
            connection.commit()
            lead_id = cursor.lastrowid
    except sqlite3.Error as error:
        event_logger.error("Database error while saving lead: %s", error)
        raise HTTPException(status_code=500, detail="Database error.") from error

    event_logger.info("New lead saved: %s", lead_id)
    return {"id": lead_id, "message": "Lead saved successfully."}
