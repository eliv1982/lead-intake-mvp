import sqlite3
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.database import get_connection, init_db
from app.logger import get_event_logger
from app.models import ErrorResponse, HealthResponse, LeadCreate, LeadResponse


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


@app.middleware("http")
async def catch_unhandled_exceptions(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Final catch-all for anything not handled by a more specific handler.

    Deliberately HTTP middleware, not `@app.exception_handler(Exception)`.
    FastAPI routes a handler registered for the bare `Exception` class to
    Starlette's outer `ServerErrorMiddleware`, which sends that handler's
    response and then *always* re-raises the original exception afterwards
    (so ASGI servers can log/track it). Under real Uvicorn, that re-raise
    lands in `RequestResponseCycle.run_asgi`'s except branch, which closes
    the transport immediately whenever a response has already started -
    racing the body write it just issued. `TestClient` does not reproduce
    this (its in-process transport just keeps whatever was sent before the
    re-raised exception is swallowed), but a real client can receive 500
    headers with a declared Content-Length and then no body. Catching the
    exception here instead - inside `call_next`, below `ServerErrorMiddleware`
    in the stack - lets us return a complete response and never re-raise, so
    `ServerErrorMiddleware` (and Uvicorn's forced transport close) is never
    reached.

    Only runs for exceptions that are neither a validation error nor an
    HTTPException (e.g. the sqlite3.Error branch below): those are handled
    further down the stack, inside `call_next`. Logs the real exception
    server-side and returns a generic JSON body so raw exception text, SQL,
    or filesystem paths never reach the client.
    """
    try:
        return await call_next(request)
    except Exception as error:
        event_logger.error("Unhandled exception on %s: %s", request.url.path, error)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error."}
        )


def custom_openapi() -> dict[str, Any]:
    """Small OpenAPI customization so the generated contract matches reality.

    The app never returns FastAPI's default 422 for request validation
    (validation errors are converted to 400 by the handler above), so the
    automatically generated 422 entry is removed from /lead's documented
    responses.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        routes=app.routes,
    )
    lead_responses = (
        schema.get("paths", {}).get("/lead", {}).get("post", {}).get("responses", {})
    )
    lead_responses.pop("422", None)

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/lead",
    response_model=LeadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "Unexpected server-side error."},
    },
)
def create_lead(lead: LeadCreate) -> LeadResponse:
    created_at = datetime.now(timezone.utc).isoformat()

    # `connection` must be closed on every exit path - success, the
    # sqlite3.Error branch below, and a post-commit `event_logger.info()`
    # exception alike - so it lives in the outer `finally`, not inside the
    # `with connection:` block (which only commits/rolls back, never
    # closes). It starts as None so the `finally` is a no-op if
    # `get_connection()` itself is what raised.
    connection = None
    try:
        try:
            connection = get_connection()
            with connection:
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

        # Best-effort diagnostic event logging: the lead above is already
        # committed at this point. If this logging call fails, the
        # exception propagates to the generic catch-all above (so the
        # client sees a 500), but the already-committed lead is NOT rolled
        # back, and the `finally` below still closes the connection. See
        # README.
        event_logger.info("New lead saved: %s", lead_id)
        return LeadResponse(id=lead_id, message="Lead saved successfully.")
    finally:
        if connection is not None:
            connection.close()
