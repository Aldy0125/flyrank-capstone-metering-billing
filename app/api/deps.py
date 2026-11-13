from collections.abc import Generator

from sqlalchemy.orm import Session

from app.config.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session for each FastAPI request.

    The session is rolled back if an exception occurs
    and always closed after the request finishes.
    """

    db = SessionLocal()

    try:
        yield db

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
