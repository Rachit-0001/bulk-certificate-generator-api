"""Test 2 - input validation (FastAPI/Pydantic answers 422 for bad input)."""
import copy

import pytest

from app.models import GenerationJob
from tests.conftest import GENERATE_URL


def error_fields(response) -> str:
    """Flatten the 'loc' of every validation error into one searchable string."""
    return " ".join(".".join(str(part) for part in err["loc"]) for err in response.json()["detail"])


def make_payload(valid_payload, **changes):
    payload = copy.deepcopy(valid_payload)
    payload.update(changes)
    return payload


def test_empty_recipients_rejected(client, valid_payload):
    response = client.post(GENERATE_URL, json=make_payload(valid_payload, recipients=[]))
    assert response.status_code == 422
    assert "recipients" in error_fields(response)


def test_missing_name_rejected(client, valid_payload):
    payload = make_payload(valid_payload, recipients=[{"email": "a@example.com"}])
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422
    assert "name" in error_fields(response)


def test_blank_name_rejected(client, valid_payload):
    payload = make_payload(valid_payload, recipients=[{"name": "   ", "email": "a@example.com"}])
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422


def test_missing_email_rejected(client, valid_payload):
    payload = make_payload(valid_payload, recipients=[{"name": "Aman"}])
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422
    assert "email" in error_fields(response)


@pytest.mark.parametrize("bad_email", ["not-an-email", "missing@tld", "@example.com", "a b@example.com"])
def test_invalid_email_rejected(client, valid_payload, bad_email):
    payload = make_payload(valid_payload, recipients=[{"name": "Aman", "email": bad_email}])
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422
    assert "Invalid email format" in response.text


def test_missing_event_name_rejected(client, valid_payload):
    payload = copy.deepcopy(valid_payload)
    del payload["event_name"]
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422
    assert "event_name" in error_fields(response)


def test_invalid_issue_date_rejected(client, valid_payload):
    response = client.post(GENERATE_URL, json=make_payload(valid_payload, issue_date="07/10/2026"))
    assert response.status_code == 422
    assert "issue_date" in error_fields(response)


def test_duplicate_emails_rejected_case_insensitively(client, valid_payload):
    payload = make_payload(
        valid_payload,
        recipients=[
            {"name": "Aman", "email": "aman@example.com"},
            {"name": "Aman Again", "email": "AMAN@example.com"},
        ],
    )
    response = client.post(GENERATE_URL, json=payload)
    assert response.status_code == 422
    assert "Duplicate recipient emails" in response.text


def test_invalid_requests_do_not_create_jobs(client, valid_payload, db_session):
    client.post(GENERATE_URL, json=make_payload(valid_payload, recipients=[]))
    assert db_session.query(GenerationJob).count() == 0


def test_whitespace_is_stripped_and_email_lowercased(client, valid_payload, db_session):
    payload = make_payload(
        valid_payload,
        event_name="  Python Workshop  ",
        recipients=[{"name": "  Rachit Gangwar  ", "email": "  Rachit@Example.COM "}],
    )
    response = client.post(GENERATE_URL, json=payload)

    assert response.status_code == 202
    job = db_session.get(GenerationJob, response.json()["job_id"])
    assert job.event_name == "Python Workshop"
    assert job.certificates[0].recipient_name == "Rachit Gangwar"
    assert job.certificates[0].recipient_email == "rachit@example.com"
