# backend/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PWD  = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "taipei")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PWD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# 使用 scoped_session，讓每個請求各自獨立
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False))
