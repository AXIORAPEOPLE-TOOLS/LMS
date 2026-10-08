"""Base Pydantic schemas used by every module."""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base for request/response bodies. Reads attributes from ORM objects."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page[ItemT](Schema):
    items: list[ItemT]
    total: int


class Message(Schema):
    message: str
