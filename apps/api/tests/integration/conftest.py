from collections.abc import Generator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.core.settings import get_settings
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.storage.minio import MinioVideoStorage


@pytest.fixture(scope="session")
def session_factory() -> sessionmaker:
    return create_session_factory(get_settings())


@pytest.fixture(scope="session")
def storage() -> MinioVideoStorage:
    adapter = MinioVideoStorage(get_settings())
    adapter.ensure_bucket()
    return adapter


@pytest.fixture(autouse=True)
def isolated_test_data(
    session_factory: sessionmaker, storage: MinioVideoStorage
) -> Generator[None]:
    with session_factory() as session:
        object_keys = list(session.scalars(select(Video.object_key)))
        session.execute(delete(Video))
        session.commit()
    for object_key in object_keys:
        storage.remove(object_key)
    yield
    with session_factory() as session:
        object_keys = list(session.scalars(select(Video.object_key)))
        session.execute(delete(Video))
        session.commit()
    for object_key in object_keys:
        storage.remove(object_key)
