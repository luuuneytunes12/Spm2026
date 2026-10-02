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

from app.domain.errors import DomainError


async def _domain_error_response(request: Request, exc: DomainError) -> JSONResponse:
    detail = (
        [{"loc": ["body", exc.field], "msg": exc.message}] if exc.field else exc.message
    )
    # The status comes from the error class itself, so this never needs to
    # know which subclasses exist.
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_response)
