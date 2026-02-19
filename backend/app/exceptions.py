"""Custom application exceptions."""
from fastapi import HTTPException, status


class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SimulationDataError(AppException):
    """Raised when required data is missing for a simulation."""
    def __init__(self, message: str, suggestion: str = ""):
        self.suggestion = suggestion
        super().__init__(message, status_code=422)


class InsufficientDataError(AppException):
    """Raised when dataset is not sufficient for a defensible prediction."""
    def __init__(self, field: str, aquifer_id: str, impact: str = ""):
        msg = (
            f"Current dataset is not sufficient to produce a defensible prediction "
            f"because missing '{field}' for aquifer {aquifer_id}."
        )
        if impact:
            msg += f" Affects uncertainty by {impact}."
        super().__init__(msg, status_code=422)


class ResourceNotFoundError(AppException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} with id '{resource_id}' not found.", status_code=404)


class DuplicateResourceError(AppException):
    def __init__(self, resource: str, field: str, value: str):
        super().__init__(
            f"{resource} with {field}='{value}' already exists.", status_code=409
        )


class AuthenticationError(AppException):
    def __init__(self, message: str = "Invalid credentials."):
        super().__init__(message, status_code=401)


class AuthorizationError(AppException):
    def __init__(self, message: str = "Insufficient permissions."):
        super().__init__(message, status_code=403)


class MLServiceError(AppException):
    """Raised when the ML microservice call fails."""
    def __init__(self, message: str = "ML service unavailable. Using stub predictions."):
        super().__init__(message, status_code=503)
