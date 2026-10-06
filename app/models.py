import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class JobStatus:
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus:
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # event_name and issue_date are the same for every certificate in a job.
    # The background task needs them later, so we store them on the job.
    event_name = Column(String, nullable=False)
    issue_date = Column(Date, nullable=False)
    status = Column(String, nullable=False, default=JobStatus.PENDING)
    total_count = Column(Integer, nullable=False, default=0)
    successful_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    certificates = relationship(
        "Certificate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.id",
    )


class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, ForeignKey("generation_jobs.id"), nullable=False, index=True)
    recipient_name = Column(String, nullable=False)
    recipient_email = Column(String, nullable=False)
    certificate_title = Column(String, nullable=False)
    status = Column(String, nullable=False, default=CertificateStatus.PENDING)
    # Stored RELATIVE to the generated/ folder (e.g. "<job_id>/12.pdf"),
    # so the database never contains real filesystem paths.
    file_path = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    job = relationship("GenerationJob", back_populates="certificates")
