from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# telling sqlalchemy where to connect within blog.db file
# when connected to postgres, this will need to change**
    # updated, sql alchemy will now use async driver for db
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./blog.db"

# connecting to db
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# factory that creates db sessions, session created per every request to db
    # expire_on_commit=False <-- recommended for async, prevents issues w/ expired objects on commit
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


# dependency function that provides session to our routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
