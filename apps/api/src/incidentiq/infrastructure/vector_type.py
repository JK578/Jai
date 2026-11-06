"""Minimal reflection support for pgvector; runtime binds use validated text casts."""

from sqlalchemy.dialects.postgresql.base import ischema_names
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions

    def get_col_spec(self, **kwargs):
        return "VECTOR" if self.dimensions is None else f"VECTOR({int(self.dimensions)})"


ischema_names.setdefault("vector", Vector)
ischema_names.setdefault("extensions.vector", Vector)
