"""What can go wrong in the domain, independent of how it is delivered.

Business rules raise these instead of FastAPI's HTTPException, so a rule
can be tested -- and reused -- without a web layer. One exception handler
(app/core/error_handlers.py) turns the hierarchy into HTTP responses, so a
new kind of failure is one subclass here and nothing changes there:
each class carries its own status code, and the handler just asks for it.
"""


class DomainError(Exception):
    """A business rule was not satisfied.

    `field` names the input at fault, when there is one, so a form can mark
    that input rather than just show a message.
    """

    status_code: int = 400

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class NotFound(DomainError):
    """No such thing -- or not one the caller may know exists.

    "Not yours" and "does not exist" deliberately use this same error, so
    ids cannot be probed to find out which ones exist.
    """

    status_code = 404


class Conflict(DomainError):
    """The request is fine, but not in the current state of things."""

    status_code = 409


class InvalidInput(DomainError):
    """A value that no state of the world could make acceptable."""

    status_code = 422


class Forbidden(DomainError):
    """The caller is known, and may not do this."""

    status_code = 403
