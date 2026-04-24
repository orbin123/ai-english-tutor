""" Database engine, session factory, and FastAPI dependency"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Engine
_db_url = settings.database_url.replace(
    "postgresql://", "postgresql+psycopg://", 1
)

engine = create_engine(
    _db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

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