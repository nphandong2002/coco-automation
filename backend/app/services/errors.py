from __future__ import annotations


class AppError(Exception):
    """Domain error translated to an HTTP response by the API layer."""

    status_code = 400

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404


class Forbidden(AppError):
    status_code = 403


class Conflict(AppError):
    status_code = 409
