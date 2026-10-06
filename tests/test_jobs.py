"""Test 1 - creating a generation job (plus a check that Swagger docs exist)."""
from app.models import GenerationJob
from app.services import certificate_service
from tests.conftest import GENERATE_URL


def test_create_job_returns_202_and_job_details(client, valid_payload, db_session):
    response = client.post(GENERATE_URL, json=valid_payload)

    assert response.status_code == 202
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "PENDING"  # status at the moment the job was created
    assert body["total_count"] == 2
    assert body["message"] == "Certificate generation started"

    job = db_session.get(GenerationJob, body["job_id"])
    assert job is not None
    assert job.total_count == 2
    assert [c.recipient_email for c in job.certificates] == ["rachit@example.com", "aman@example.com"]


def test_post_only_schedules_work_and_does_not_generate_inline(
    client, valid_payload, db_session, monkeypatch
):
    """Replace the background processor with a no-op: the job must stay PENDING."""
    monkeypatch.setattr(certificate_service, "process_job", lambda job_id: None)

    response = client.post(GENERATE_URL, json=valid_payload)

    assert response.status_code == 202
    job = db_session.get(GenerationJob, response.json()["job_id"])
    assert job.status == "PENDING"
    assert all(c.status == "PENDING" for c in job.certificates)


def test_swagger_and_redoc_are_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200

    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/certificates/generate" in paths
    assert "/api/v1/certificates/jobs/{job_id}" in paths
    assert "/api/v1/certificates/jobs/{job_id}/results" in paths
    assert "/api/v1/certificates/{certificate_id}/download" in paths
