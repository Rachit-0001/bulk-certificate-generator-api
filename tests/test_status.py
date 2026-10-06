"""Test 4 (job status) and Test 7 (job not found)."""
from app import crud
from app.schemas import GenerationRequest

STATUS_URL = "/api/v1/certificates/jobs/{}"


def test_status_of_finished_job(client, generate):
    job_id = generate().json()["job_id"]

    response = client.get(STATUS_URL.format(job_id))

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["status"] == "COMPLETED"
    assert body["total_count"] == 2
    assert body["successful_count"] == 2
    assert body["failed_count"] == 0
    assert body["pending_count"] == 0
    assert body["created_at"] is not None
    assert body["completed_at"] is not None


def test_pending_count_is_total_minus_successful_minus_failed(client, db_session, valid_payload):
    """Simulate a job that is half-way through by editing the counters directly."""
    valid_payload["recipients"] = [
        {"name": f"User {i}", "email": f"user{i}@example.com"} for i in range(10)
    ]
    job = crud.create_job(db_session, GenerationRequest(**valid_payload))
    job.status = "PROCESSING"
    job.successful_count = 6
    job.failed_count = 1
    db_session.commit()

    body = client.get(STATUS_URL.format(job.id)).json()

    assert body["status"] == "PROCESSING"
    assert body["total_count"] == 10
    assert body["successful_count"] == 6
    assert body["failed_count"] == 1
    assert body["pending_count"] == 3
    assert body["completed_at"] is None


def test_status_of_unknown_job_returns_404(client):
    response = client.get(STATUS_URL.format("does-not-exist"))
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_results_of_unknown_job_returns_404(client):
    response = client.get(STATUS_URL.format("does-not-exist") + "/results")
    assert response.status_code == 404


def test_results_list_every_certificate(client, generate):
    job_id = generate().json()["job_id"]

    body = client.get(STATUS_URL.format(job_id) + "/results").json()

    assert body["job_id"] == job_id
    assert len(body["certificates"]) == 2
    first = body["certificates"][0]
    assert first["recipient_name"] == "Rachit Gangwar"
    assert first["email"] == "rachit@example.com"
    assert first["status"] == "SUCCESS"
    assert first["download_url"] == f"/api/v1/certificates/{first['certificate_id']}/download"
    assert first["error_message"] is None
