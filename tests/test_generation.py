"""Test 3 - PDF certificate generation."""
from datetime import date

from app.models import GenerationJob
from app.services import certificate_service


def test_generate_certificate_creates_readable_pdf(tmp_path):
    output = tmp_path / "one.pdf"

    result = certificate_service.generate_certificate(
        output_path=output,
        recipient_name="Rachit Gangwar",
        event_name="Python Programming Workshop",
        certificate_title="Certificate of Completion",
        issue_date=date(2026, 10, 7),
        certificate_code="ABCD1234-00001",
    )

    assert result == output and output.exists()
    content = output.read_bytes()
    assert content.startswith(b"%PDF")
    assert content.rstrip().endswith(b"%%EOF")
    for expected_text in [b"Rachit Gangwar", b"Python Programming Workshop", b"07 Oct 2026", b"ABCD1234-00001"]:
        assert expected_text in content


def test_very_long_names_still_generate(tmp_path):
    output = tmp_path / "long.pdf"
    certificate_service.generate_certificate(
        output_path=output,
        recipient_name="A" * 80,
        event_name="B" * 100,
        certificate_title="C" * 50,
        issue_date=date(2026, 10, 7),
    )
    assert output.stat().st_size > 0


def test_background_job_generates_all_certificates(generate, db_session, output_dir):
    response = generate()
    job_id = response.json()["job_id"]

    job = db_session.get(GenerationJob, job_id)
    assert job.status == "COMPLETED"
    assert job.completed_at is not None

    for certificate in job.certificates:
        assert certificate.status == "SUCCESS"
        assert certificate.error_message is None
        pdf_file = output_dir / certificate.file_path
        assert pdf_file.exists()
        content = pdf_file.read_bytes()
        assert content.startswith(b"%PDF")
        assert certificate.recipient_name.encode() in content


def test_stored_file_path_is_relative(generate, db_session):
    job = db_session.get(GenerationJob, generate().json()["job_id"])
    stored = job.certificates[0].file_path
    assert stored == f"{job.id}/{job.certificates[0].id}.pdf"
