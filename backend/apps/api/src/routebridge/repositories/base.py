from typing import Generic, TypeVar

from sqlmodel import SQLModel

ModelT = TypeVar("ModelT", bound=SQLModel)


class Repository(Generic[ModelT]):
    """Small extension point for tenant-scoped persistence implementations."""

    model: type[ModelT]
