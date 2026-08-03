"""Dialect-aware UUID compatibility layer.

PostgreSQL: native UUID type (with or without as_uuid).
SQLite: stores as CHAR(36) with dashes so string comparisons work consistently
        and both uuid.UUID objects and hyphenated strings bind correctly.
"""
from __future__ import annotations

import uuid

from sqlalchemy import String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as _PGUUID


class UUID(TypeDecorator):
    """Drop-in replacement for sqlalchemy.dialects.postgresql.UUID.

    Usage in models is identical: ``Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)``.
    """

    impl = String(36)
    cache_ok = True

    def __init__(self, as_uuid: bool = True, **kwargs):
        self.as_uuid = as_uuid
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PGUUID(as_uuid=self.as_uuid))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            parsed = value
        else:
            parsed = uuid.UUID(value)
        if dialect.name == "postgresql":
            return parsed
        return str(parsed)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if self.as_uuid:
            # PostgreSQL/asyncpg may return its own UUID object; SQLite returns a string.
            if isinstance(value, uuid.UUID):
                return value
            try:
                return uuid.UUID(str(value))
            except ValueError:
                return value
        return str(value)
