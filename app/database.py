import os
import ssl
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured in the environment")

url = make_url(DATABASE_URL)
connect_args = {}
engine_options = {}
if url.drivername in {"postgresql", "postgres", "postgresql+pg8000"}:
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    url = url.set(drivername="postgresql+pg8000", query=query)
    if sslmode != "disable":
        certificate_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "certs", "prod-ca-2021.crt")
        )
        ssl_context = ssl.create_default_context()
        ssl_context.load_verify_locations(cafile=certificate_path)
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.check_hostname = True
        connect_args["ssl_context"] = ssl_context
    engine_options.update(
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_recycle=300,
        pool_timeout=10,
    )
elif url.drivername == "sqlite":
    connect_args["check_same_thread"] = False

engine = create_engine(url, connect_args=connect_args, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
