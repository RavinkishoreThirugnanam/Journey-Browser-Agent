from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str


class ListResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    count: int = 0
