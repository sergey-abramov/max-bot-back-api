from dataclasses import dataclass
from typing import Any


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] | None = None


def to_error_response(request_id: str, err: ApiError) -> dict[str, Any]:
    return {
        "error": {
            "code": err.code,
            "message": err.message,
            "requestId": request_id,
            "details": err.details or {},
        }
    }
