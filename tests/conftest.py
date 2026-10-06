"""Shared test setup.

Every test gets:
  * its own temporary SQLite database file (the real certificates.db is never touched)
  * its own temporary output folder (the real generated/ folder is never touched)
  * a FastAPI TestClient wired to both

The trick: app code always calls `database.SessionLocal()` at run time, so
swapping that one name (monkeypatch) redirects BOTH the request handlers
and the background task to the test database.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.database import Base
from app.main import app
from app.services import certificate_service

GENERATE_URL = "/api/v1/certificates/generate"


@pytest.fixture()
def test_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(test_engine, monkeypatch):
    factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    return factory


@pytest.fixture()
def db_session(session_factory):
    """A session the tests can use to look directly inside the test database."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def output_dir(tmp_path, monkeypatch):
    folder = tmp_path / "generated"
    monkeypatch.setattr(certificate_service, "OUTPUT_DIR", folder)
    return folder


@pytest.fixture()
def client(session_factory, output_dir):
    # No `with` block, so the startup hook (which touches the real DB) is not run.
    # Note: TestClient runs background tasks BEFORE returning the response to the test.
    return TestClient(app)


@pytest.fixture()
def valid_payload():
    return {
        "event_name": "Python Programming Workshop",
        "certificate_title": "Certificate of Completion",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Rachit Gangwar", "email": "rachit@example.com"},
            {"name": "Aman Kumar", "email": "aman@example.com"},
        ],
    }


@pytest.fixture()
def generate(client, valid_payload):
    """Helper: POST a request and return the response (optionally with custom names)."""

    def _generate(names=None):
        payload = dict(valid_payload)
        if names is not None:
            payload["recipients"] = [
                {"name": name, "email": f"user{i}@example.com"} for i, name in enumerate(names)
            ]
        return client.post(GENERATE_URL, json=payload)

    return _generate
