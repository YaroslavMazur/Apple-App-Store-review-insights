from __future__ import annotations


class DomainError(Exception):
    """Base for typed errors mapped to HTTP responses by the global exception handler."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidInputError(DomainError):
    status_code = 400
    code = "invalid_input"


class AppNotFoundError(DomainError):
    status_code = 404
    code = "app_not_found"


class UpstreamUnavailableError(DomainError):
    status_code = 502
    code = "upstream_unavailable"
