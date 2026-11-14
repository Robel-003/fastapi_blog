from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# telling sqlalchemy where to connect within blog.db file
# when connected to postgres, this will need to change**
SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"

# connecting to db
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# factory that creates db sessions, session created per every request to db
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# dependency function that provides session to our routes
def get_db():
    with SessionLocal() as db:
        yield db
