"""All database reads/writes live here, so routes and services stay short."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Certificate, CertificateStatus, GenerationJob, JobStatus, utc_now
from app.schemas import GenerationRequest


def create_job(db: Session, request: GenerationRequest) -> GenerationJob:
    """Create the job and one PENDING certificate per recipient in a single commit."""
    job = GenerationJob(
        event_name=request.event_name,
        issue_date=request.issue_date,
        total_count=len(request.recipients),
        certificates=[
            Certificate(
                recipient_name=recipient.name,
                recipient_email=recipient.email,
                certificate_title=request.certificate_title,
            )
            for recipient in request.recipients
        ],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Optional[GenerationJob]:
    return db.get(GenerationJob, job_id)


def get_certificate(db: Session, certificate_id: int) -> Optional[Certificate]:
    return db.get(Certificate, certificate_id)


def mark_job_processing(db: Session, job: GenerationJob) -> None:
    job.status = JobStatus.PROCESSING
    db.commit()


def mark_certificate_success(
    db: Session, job: GenerationJob, certificate: Certificate, file_path: str
) -> None:
    certificate.status = CertificateStatus.SUCCESS
    certificate.file_path = file_path
    job.successful_count += 1
    db.commit()  # commit per certificate so progress is visible while the job runs


def mark_certificate_failed(
    db: Session, job: GenerationJob, certificate: Certificate, error_message: str
) -> None:
    certificate.status = CertificateStatus.FAILED
    certificate.error_message = error_message[:500]
    job.failed_count += 1
    db.commit()


def finish_job(db: Session, job: GenerationJob) -> None:
    """Pick the final status once every certificate has been attempted."""
    if job.failed_count == 0:
        job.status = JobStatus.COMPLETED
    else:
        # Some (or all) certificates failed, but the job itself ran to the end.
        job.status = JobStatus.COMPLETED_WITH_ERRORS
    job.completed_at = utc_now()
    db.commit()


def mark_job_failed(db: Session, job_id: str) -> None:
    """Used only when the job as a whole could not be processed."""
    job = db.get(GenerationJob, job_id)
    if job is not None:
        job.status = JobStatus.FAILED
        job.completed_at = utc_now()
        db.commit()
