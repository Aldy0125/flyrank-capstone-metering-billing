import pytest

from sqlalchemy.orm import Session

from app.config.database import engine


@pytest.fixture
def db_session():
    """
    Provide an isolated database session.

    Each test runs inside a transaction that is rolled back
    after the test finishes.
    """

    connection = engine.connect()
    transaction = connection.begin()

    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()

        if transaction.is_active:
            transaction.rollback()

        connection.close()
