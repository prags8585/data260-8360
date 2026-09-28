import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://root:hw4pass@localhost:3306/s8360_rel",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

db_session_basede26 = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = db_session_basede26()
    try:
        yield db
    finally:
        db.close()
