from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, BigInteger, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.app.config import Settings


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "pipeline_run"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="cli")
    started_at: Mapped[str] = mapped_column(String(32), index=True)
    finished_at: Mapped[str | None] = mapped_column(String(32))
    duration: Mapped[float | None] = mapped_column(Float)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    bytes_written: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Task(Base):
    __tablename__ = "task_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[str] = mapped_column(String(32))
    finished_at: Mapped[str | None] = mapped_column(String(32))
    seconds: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)


class Quality(Base):
    __tablename__ = "quality_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    dataset: Mapped[str] = mapped_column(String(40))
    rule_id: Mapped[str] = mapped_column(String(50))
    rule_name: Mapped[str] = mapped_column(String(100))
    evaluated: Mapped[int] = mapped_column(Integer)
    failed: Mapped[int] = mapped_column(Integer)
    pass_rate: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(12))
    evaluated_at: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20))


class Manifest(Base):
    __tablename__ = "source_manifest"

    dataset: Mapped[str] = mapped_column(String(40), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    key: Mapped[str] = mapped_column(String(150))
    source_file: Mapped[str] = mapped_column(String(200))
    rows: Mapped[int] = mapped_column(Integer)
    watermark: Mapped[str | None] = mapped_column(String(32))


class State(Base):
    __tablename__ = "publication_state"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))


class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(12))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        options = {"check_same_thread": False, "timeout": 20} if settings.database_url.startswith("sqlite") else {}
        self.engine = create_engine(settings.database_url, connect_args=options, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", self._enable_foreign_keys)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys = ON")

    def migrate(self):
        self.settings.home.mkdir(parents=True, exist_ok=True)
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    @contextmanager
    def transaction(self):
        with self.sessions.begin() as session:
            yield session


def serialize(row: Base) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def published_run(session: Session) -> str | None:
    state = session.get(State, "published_run")
    return state.value if state else None
