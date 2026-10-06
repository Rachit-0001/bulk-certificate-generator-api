import re
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Deliberately simple: something@something.something with no spaces.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Upper limit protects the server: BackgroundTasks runs inside the API process.
MAX_RECIPIENTS = 1000


class Recipient(BaseModel):
    # Strips leading/trailing whitespace from every string field *before* validation.
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=80, examples=["Rachit Gangwar"])
    email: str = Field(..., min_length=1, max_length=254, examples=["rachit@example.com"])

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value):
            raise ValueError("Invalid email format (expected something like name@example.com)")
        return value.lower()  # lowercase so duplicates are detected reliably


class GenerationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_name: str = Field(..., min_length=1, max_length=100, examples=["Python Programming Workshop"])
    certificate_title: str = Field(
        default="Certificate of Completion", min_length=1, max_length=50
    )
    issue_date: date = Field(..., examples=["2026-10-07"])
    recipients: List[Recipient] = Field(
        ...,
        min_length=1,
        max_length=MAX_RECIPIENTS,
        description=f"Between 1 and {MAX_RECIPIENTS} recipients.",
    )

    @field_validator("recipients")
    @classmethod
    def reject_duplicate_emails(cls, recipients: List[Recipient]) -> List[Recipient]:
        seen = set()
        duplicates = []
        for recipient in recipients:
            if recipient.email in seen and recipient.email not in duplicates:
                duplicates.append(recipient.email)
            seen.add(recipient.email)
        if duplicates:
            raise ValueError(f"Duplicate recipient emails in request: {', '.join(duplicates)}")
        return recipients


class GenerationResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    successful_count: int
    failed_count: int
    pending_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None


class CertificateResult(BaseModel):
    certificate_id: int
    recipient_name: str
    email: str
    status: str
    download_url: Optional[str] = None
    error_message: Optional[str] = None


class JobResultsResponse(BaseModel):
    job_id: str
    certificates: List[CertificateResult]
