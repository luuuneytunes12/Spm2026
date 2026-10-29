"""Turning domain errors into HTTP responses -- the one place that knows how.

The body follows the two shapes the rest of the API already uses, so the
frontend's existing error handling works unchanged:

  * an error about one input is a list in FastAPI's own validation shape,
    `[{"loc": ["body", "<field>"], "msg": "..."}]`, which `ApiError.fields`
    reads to mark that input
  * anything else is a plain `{"detail": "..."}` string
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.domain.errors import DomainError, ImmutableRecord
from app.models.events import ACTIVITY_LOG_IMMUTABLE_MESSAGE

# Raised by the event_status_history trigger
# (supabase/migrations/20261027150209_event_workflow_stories.sql).
_ACTIVITY_LOG_TRIGGER_MESSAGE = "Event activity log entries are immutable"


async def _domain_error_response(request: Request, exc: DomainError) -> JSONResponse:
    detail = (
        [{"loc": ["body", exc.field], "msg": exc.message}] if exc.field else exc.message
    )
    # The status comes from the error class itself, so this never needs to
    # know which subclasses exist.
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


async def _database_error_response(request: Request, exc: DBAPIError) -> JSONResponse:
    """The database's own refusal to edit the Activity Log, worded like the
    ORM's. Any other database error is not ours to explain and stays a 500."""
    if _ACTIVITY_LOG_TRIGGER_MESSAGE not in str(exc.orig):
        raise exc
    return await _domain_error_response(
        request, ImmutableRecord(ACTIVITY_LOG_IMMUTABLE_MESSAGE)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_response)
    app.add_exception_handler(DBAPIError, _database_error_response)
