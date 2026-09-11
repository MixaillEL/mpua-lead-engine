import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@pytest.fixture(scope="session")
def engine():
    settings = get_settings()
    return create_engine(settings.test_database_url, future=True)


@pytest.fixture()
def db_session(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, future=True)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def committing_db_session(engine) -> Session:
    """A plain session (own connection/transactions) for services that call
    commit()/begin_nested() themselves, e.g. source_runner. Tests using this
    fixture are responsible for deleting the rows they create; deleting a
    Job cascades (DB-level ON DELETE CASCADE) to its Source/RawRecord rows.
    """
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
