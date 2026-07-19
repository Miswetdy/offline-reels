from sqlalchemy import create_engine, text

from app.core.settings import Settings


def check_postgres(settings: Settings) -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()
