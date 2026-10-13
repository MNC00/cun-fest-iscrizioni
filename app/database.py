import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL deve essere configurata come variabile d'ambiente.")

database_url = make_url(DATABASE_URL)
if database_url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
    database_url = database_url.set(drivername="postgresql+psycopg2")

engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
