from typing import Any, Dict, Optional

from fastapi import status
from pydantic import BaseModel, Field


class Error(BaseModel):
    code: int = Field(..., description="Error code")
    description: str = Field(..., description="Error description")
    message: Optional[str] = Field(None, description="Custom Error message")


class NotFoundError(Error):
    code: int = status.HTTP_404_NOT_FOUND
    description: str = "Not found"


class BadRequestError(Error):
    code: int = status.HTTP_400_BAD_REQUEST
    description: str = "Bad Request"


class EnityConflictError(Error):
    code: int = status.HTTP_409_CONFLICT
    description: str = "An entity conflict occurred"


class UnauthorizedError(Error):
    code: int = status.HTTP_401_UNAUTHORIZED
    description: str = "Unauthorized"


class ServiceUnavailableError(Error):
    code: int = status.HTTP_503_SERVICE_UNAVAILABLE
    description: str = "Service Unavailable"


fastAPIErrorResponseModels: Dict[int | str, Dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"model": NotFoundError},
    status.HTTP_400_BAD_REQUEST: {"model": BadRequestError},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": Error},
    status.HTTP_409_CONFLICT: {"model": EnityConflictError},
    status.HTTP_401_UNAUTHORIZED: {"model": UnauthorizedError},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ServiceUnavailableError},
}
