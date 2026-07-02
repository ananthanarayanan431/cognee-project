from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from debatemind.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Production resilience: managed Postgres / pgbouncer often drop idle
    # connections. pool_pre_ping validates a connection before use, and
    # pool_recycle proactively refreshes connections older than 30 minutes,
    # preventing intermittent "server closed the connection" errors.
    pool_pre_ping=True,
    pool_recycle=1800,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
