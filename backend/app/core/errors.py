"""A single error type that carries a user-friendly message and a suggested fix.

Routes convert AppError into a JSON response; anything else becomes a generic
500 so raw stack traces never reach the user.
"""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "hint": self.hint}}
