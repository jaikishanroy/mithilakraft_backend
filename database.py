import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = os.getenv("DB_NAME", "aartikraft_backend")
DB_USER = os.getenv("DB_USER", "jai")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD", "Password@2024"))
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() == "false"

# if USE_SQLITE or not DB_HOST:
#     SQLALCHEMY_DATABASE_URL = f"sqlite:///{BASE_DIR / 'aartikraft_fastbackend.db'}"
# else:
#     SQLALCHEMY_DATABASE_URL = (
#         f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
#     )
SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
