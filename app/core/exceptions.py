from typing import Any


class AppError(Exception):
    """Base class for all domain errors raised by the service layer."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_payload(self) -> dict:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class BusinessRuleError(AppError):
    status_code = 400
    code = "business_rule_violation"


class InsufficientStockError(BusinessRuleError):
    code = "insufficient_stock"