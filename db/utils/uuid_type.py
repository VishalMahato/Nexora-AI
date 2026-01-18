"""Cross-database compatible UUID type for SQLAlchemy."""
import uuid as uuid_module
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, TypeEngine


class UUIDType(TypeDecorator):
    """
    A UUID type that uses native UUID on PostgreSQL and String(36) on other databases.
    
    This allows tests to run with SQLite while production uses PostgreSQL.
    """
    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect) -> TypeEngine:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid_module.UUID):
                return str(value)
            return value
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if not isinstance(value, uuid_module.UUID):
                return uuid_module.UUID(value)
            return value
        return value
