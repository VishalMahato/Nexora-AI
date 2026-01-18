"""Cross-database compatible JSON type for SQLAlchemy."""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator, TypeEngine


class JSONType(TypeDecorator):
    """
    A JSON type that uses JSONB on PostgreSQL and JSON on other databases.
    
    This allows tests to run with SQLite while production uses PostgreSQL.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect) -> TypeEngine:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())
