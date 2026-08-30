"""Database engine, session factory, and FastAPI dependency"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.azure_postgres import install_azure_postgres_auth
from app.core.config import settings

# Engine
_db_url = make_url(settings.database_url)
if _db_url.drivername == "postgresql":
    _db_url = _db_url.set(drivername="postgresql+psycopg")


def apply_configured_database_auth(bind: Engine) -> Engine:
    """Attach Entra token injection when production uses managed identity.

    Alembic builds its own engine; it must call this or migrations connect
    without a password and fail against Azure PostgreSQL.
    """
    if settings.DATABASE_AUTH_MODE == "azure-managed-identity":
        install_azure_postgres_auth(bind)
    return bind


engine = create_engine(
    _db_url,
    echo=settings.sql_echo,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
)
apply_configured_database_auth(engine)

# Session Factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# Declarative Base
class Base(DeclarativeBase):
    """Base Class for all ORM Models"""

    pass


# FastAPI Dependency
def get_db() -> Generator[Session, None, None]:
    """
    Provide a SQLAlchemy session for one request.

    Usage in a route:
        def my_handler(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
