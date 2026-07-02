from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .error_codes import Error

DataT = TypeVar("DataT")


class Response(BaseModel, Generic[DataT]):
    success: bool = Field(..., description="Success status of the response")
    data: DataT | None = Field(None, description="Data to return in the response of type T")


class SuccessResponse(Response[DataT]):
    success: bool = True
    data: DataT = Field(..., description="Data to return in the response of type T")


class ErrorResponse(Exception):
    def __init__(self, error: Error):
        super().__init__(error.message)
        self.error = error

    def __str__(self):
        return f"[Error {self.error.code}]: {self.error.description}"
