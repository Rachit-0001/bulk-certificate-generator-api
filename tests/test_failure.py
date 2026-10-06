"""Test 5 - one failing recipient must not stop the others."""
import pytest
from fastapi.testclient import TestClient

from app import crud
from app.main import app
from app.services import certificate_service

STATUS_URL = "/api/v1/certificates/jobs/{}"


@pytest.fixture()
def fail_for(monkeypatch):
    """Make generate_certificate raise for the given recipient names only."""
    real_function = certificate_service.generate_certificate

    def install(*bad_names):
        def fake_generate(**kwargs):
            if kwargs["recipient_name"] in bad_names:
                raise RuntimeError("Simulated PDF error")
            return real_function(**kwargs)

        monkeypatch.setattr(certificate_service, "generate_certificate", fake_generate)

    return install


def test_one_failure_does_not_stop_the_job(client, generate, fail_for, output_dir):
    fail_for("Recipient Two")

    job_id = generate(["Recipient One", "Recipient Two", "Recipient Three"]).json()["job_id"]

    status = client.get(STATUS_URL.format(job_id)).json()
    assert status["status"] == "COMPLETED_WITH_ERRORS"
    assert status["total_count"] == 3
    assert status["successful_count"] == 2
    assert status["failed_count"] == 1
    assert status["pending_count"] == 0

    first, second, third = client.get(STATUS_URL.format(job_id) + "/results").json()["certificates"]
    assert first["status"] == "SUCCESS"
    assert second["status"] == "FAILED"
    assert "Simulated PDF error" in second["error_message"]
    assert second["download_url"] is None
    # The important one: the recipient AFTER the failure was still processed.
    assert third["status"] == "SUCCESS"
    assert third["download_url"] is not None
    assert len(list(output_dir.rglob("*.pdf"))) == 2


def test_failure_of_first_recipient_does_not_block_the_rest(client, generate, fail_for):
    fail_for("Recipient One")
    job_id = generate(["Recipient One", "Recipient Two"]).json()["job_id"]

    status = client.get(STATUS_URL.format(job_id)).json()
    assert (status["successful_count"], status["failed_count"]) == (1, 1)


def test_job_with_every_certificate_failing_is_completed_with_errors(client, generate, fail_for):
    fail_for("A", "B", "C")
    job_id = generate(["A", "B", "C"]).json()["job_id"]

    status = client.get(STATUS_URL.format(job_id)).json()
    assert status["status"] == "COMPLETED_WITH_ERRORS"
    assert status["successful_count"] == 0
    assert status["failed_count"] == 3


def test_job_that_cannot_run_at_all_is_marked_failed(client, generate, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(crud, "mark_job_processing", broken)

    job_id = generate().json()["job_id"]

    status = client.get(STATUS_URL.format(job_id)).json()
    assert status["status"] == "FAILED"
    assert status["completed_at"] is not None
    assert status["pending_count"] == 2  # nothing was processed


def test_unexpected_server_error_returns_500_json(session_factory, output_dir, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(crud, "get_job", broken)
    # raise_server_exceptions=False lets the test see the 500 response instead of the exception
    safe_client = TestClient(app, raise_server_exceptions=False)

    response = safe_client.get(STATUS_URL.format("anything"))

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
