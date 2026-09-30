"""Fixtures for tests that run against a REAL PostgreSQL engine.

The unit tests one directory up use in-memory SQLite, which is fast but
cannot answer the questions this layer exists for: does the story hold on
the production engine (its constraints, enum/timestamp handling, foreign
keys) and -- above all -- does it hold when two requests arrive at the same
moment? SQLite serialises every write, so a race that Postgres exposes is
invisible to it.

The database is a disposable `postgres:16` container started by
Testcontainers and built from the project's own `db/schema.sql`. Nothing
here can reach the team's Supabase project: the engine is constructed from
the container's URL, never from `app.core.db.engine`.

If Docker is unavailable the tests SKIP with a reason -- unless
REQUIRE_INTEGRATION=1 (set in CI), in which case that is a hard failure so
the layer cannot quietly stop running.
"""

import os
import re
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import get_db
from app.core.roles import Role
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"

COMPLETE_EVENT = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "accessibility_needs": "Step-free access, hearing loop",
    "equipment_requirements": "2 projectors, 4 radio mics",
}


def pytest_collection_modifyitems(items):
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


def _unavailable(reason: str):
    if os.environ.get("REQUIRE_INTEGRATION") == "1":
        pytest.fail(f"Integration tests are required but cannot run: {reason}")
    pytest.skip(f"Integration tests need PostgreSQL: {reason}")


@pytest.fixture(scope="session")
def pg_engine() -> Generator[Engine, None, None]:
    """A SQLAlchemy engine on a throwaway Postgres with the real schema."""
    override = os.environ.get("INTEGRATION_DATABASE_URL")
    container = None
    if override:
        # Same guard as frontend/playwright.config.ts: these tests TRUNCATE
        # every table, so anything that is not local is refused outright.
        if not re.search(r"@(localhost|127\.0\.0\.1)[:/]", override):
            pytest.fail(f"Refusing to run integration tests against a non-local database: {override}")
        url = override
    else:
        try:
            try:
                from testcontainers.community.postgres import PostgresContainer
            except ImportError:  # older testcontainers
                from testcontainers.postgres import PostgresContainer

            container = PostgresContainer("postgres:16", driver="psycopg")
            container.start()
        except Exception as exc:  # Docker missing / not running / image pull failed
            _unavailable(f"could not start a container ({type(exc).__name__}: {exc})")
        url = container.get_connection_url()

    engine = create_engine(url, pool_pre_ping=True, pool_size=20, max_overflow=20)
    try:
        # schema.sql is several statements; the driver's simple-query path
        # runs them as one script.
        raw = engine.raw_connection()
        try:
            raw.cursor().execute(SCHEMA_SQL.read_text())
            raw.commit()
        finally:
            raw.close()
        yield engine
    finally:
        engine.dispose()
        if container is not None:
            container.stop()


@pytest.fixture()
def session_factory(pg_engine: Engine) -> Generator[sessionmaker, None, None]:
    """A clean database for each test, and a way to open fresh sessions."""
    with pg_engine.begin() as conn:
        tables = conn.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        ).scalars().all()
        if tables:
            conn.execute(text("truncate " + ", ".join(f'"{t}"' for t in tables) + " restart identity cascade"))
    yield sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


@pytest.fixture()
def db(session_factory: sessionmaker) -> Generator[Session, None, None]:
    """A session for the TEST to seed and inspect data with."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_client(session_factory: sessionmaker) -> Generator[Callable[[], TestClient], None, None]:
    """Factory for API clients whose every request gets its OWN session,
    exactly as in production (the SQLite tests share one). Concurrency tests
    take one client per thread."""

    def _get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    yield lambda: TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def client(make_client) -> TestClient:
    return make_client()


@pytest.fixture()
def make_user(db: Session) -> Callable[..., tuple[User, dict[str, str]]]:
    """Insert a user with `role` and return (user, auth headers)."""

    def _make(role: Role, email: str, name: str = "Test User", *, available: bool = True):
        user = User(
            name=name,
            email=email,
            password_hash=hash_password("password123"),
            role=role.value,
            is_available=available,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(user.id, user.role)
        return user, {"Authorization": f"Bearer {token}"}

    return _make


def submit_event(client: TestClient, organiser_headers: dict[str, str], **overrides) -> int:
    """Create a complete draft and submit it; returns the event id."""
    created = client.post("/events", json={**COMPLETE_EVENT, **overrides}, headers=organiser_headers)
    assert created.status_code == 201, created.text
    event_id = created.json()["id"]
    submitted = client.post(f"/events/{event_id}/submit", headers=organiser_headers)
    assert submitted.status_code == 200, submitted.text
    return event_id
