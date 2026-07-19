from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session_factory(request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def get_session(request) -> Generator[Session]:
    session = get_session_factory(request)()
    try:
        yield session
    finally:
        session.close()
