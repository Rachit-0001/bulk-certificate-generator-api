"""Test 6 - downloading certificates."""
from app.models import Certificate


def get_results(client, job_id):
    return client.get(f"/api/v1/certificates/jobs/{job_id}/results").json()["certificates"]


def test_download_returns_pdf(client, generate):
    job_id = generate().json()["job_id"]
    certificate = get_results(client, job_id)[0]

    response = client.get(certificate["download_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "certificate_" in response.headers["content-disposition"]


def test_download_unknown_certificate_returns_404(client):
    response = client.get("/api/v1/certificates/99999/download")
    assert response.status_code == 404


def test_download_of_failed_certificate_returns_409(client, generate, db_session):
    job_id = generate().json()["job_id"]
    certificate_id = get_results(client, job_id)[0]["certificate_id"]
    certificate = db_session.get(Certificate, certificate_id)
    certificate.status = "FAILED"
    certificate.error_message = "Certificate generation failed: test"
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{certificate_id}/download")

    assert response.status_code == 409
    assert "FAILED" in response.json()["detail"]


def test_download_when_file_was_deleted_returns_404(client, generate, output_dir):
    job_id = generate().json()["job_id"]
    certificate = get_results(client, job_id)[0]
    for pdf_file in output_dir.rglob("*.pdf"):
        pdf_file.unlink()

    response = client.get(certificate["download_url"])

    assert response.status_code == 404


def test_download_never_serves_files_outside_generated_folder(client, generate, db_session, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    job_id = generate().json()["job_id"]
    certificate_id = get_results(client, job_id)[0]["certificate_id"]
    certificate = db_session.get(Certificate, certificate_id)
    certificate.file_path = "../secret.txt"  # simulate a tampered database value
    db_session.commit()

    response = client.get(f"/api/v1/certificates/{certificate_id}/download")

    assert response.status_code == 404
    assert "top secret" not in response.text
