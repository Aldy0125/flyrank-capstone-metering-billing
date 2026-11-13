from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings


# SQLAlchemy database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


# Database session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)
