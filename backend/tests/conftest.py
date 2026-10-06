import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.main import app

# Tests register and log in several users each, and the production bcrypt cost
# (about 250ms per hash and 215ms per check) made that most of the suite's
# runtime. bcrypt's minimum cost (4 rounds) is plenty for tests. This replaces
# the hashing context for the test process only; production is unaffected, and
# passwords hashed in production still verify there. The e2e backend is a
# separate process and keeps the real cost.
from passlib.context import CryptContext  # noqa: E402

import app.core.security as _security  # noqa: E402

_security._pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def coordinator_auto_assign(monkeypatch):
    """Make submitting an event assign a Coordinator again, as it did before
    assignment became the Event Coordinator Lead's job.

    For the older coordinator-workflow tests, which need an event that is
    already assigned as their starting point (and, in test_coordinator_
    assignment.py, test what assignment itself does). It runs the real
    `assign_coordinator`, so notifications, the activity log and the
    least-loaded rule are exercised exactly as in production. Tests of the
    Lead's queue do NOT use it: there, submit leaves the event unassigned.
    """
    from app.routers import events as events_router
    from app.services.assignment import assign_coordinator

    monkeypatch.setattr(
        events_router,
        "_after_submit",
        lambda db, event, user: assign_coordinator(db, event, actor_id=user.id),
    )
