from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.models import CertificateStatus, GenerationJob
from app.schemas import (
    CertificateResult,
    GenerationRequest,
    GenerationResponse,
    JobResultsResponse,
    JobStatusResponse,
)
from app.services import certificate_service

router = APIRouter(prefix="/api/v1/certificates", tags=["Certificates"])


def get_job_or_404(db: Session, job_id: str) -> GenerationJob:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.post(
    "/generate",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a bulk certificate generation job",
    description=(
        "Validates the request, creates a job plus one PENDING certificate per recipient, "
        "and returns immediately with a job ID. The PDFs are generated in the background. "
        "Use the job status endpoint to follow progress."
    ),
)
def generate_certificates(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GenerationResponse:
    job = crud.create_job(db, request)
    background_tasks.add_task(certificate_service.process_job, job.id)
    return GenerationResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        message="Certificate generation started",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and progress",
    description="pending_count is calculated as total_count - successful_count - failed_count.",
    responses={404: {"description": "Job not found"}},
)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = get_job_or_404(db, job_id)
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        successful_count=job.successful_count,
        failed_count=job.failed_count,
        pending_count=job.total_count - job.successful_count - job.failed_count,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get(
    "/jobs/{job_id}/results",
    response_model=JobResultsResponse,
    summary="List every certificate in a job",
    description="Shows each recipient's status. Successful ones include a download_url; failed ones include an error_message.",
    responses={404: {"description": "Job not found"}},
)
def get_job_results(job_id: str, db: Session = Depends(get_db)) -> JobResultsResponse:
    job = get_job_or_404(db, job_id)
    results = [
        CertificateResult(
            certificate_id=certificate.id,
            recipient_name=certificate.recipient_name,
            email=certificate.recipient_email,
            status=certificate.status,
            download_url=(
                f"/api/v1/certificates/{certificate.id}/download"
                if certificate.status == CertificateStatus.SUCCESS
                else None
            ),
            error_message=certificate.error_message,
        )
        for certificate in job.certificates
    ]
    return JobResultsResponse(job_id=job.id, certificates=results)


@router.get(
    "/{certificate_id}/download",
    summary="Download a generated certificate (PDF)",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The certificate PDF"},
        404: {"description": "Certificate or its file not found"},
        409: {"description": "Certificate is not available (failed or still pending)"},
    },
)
def download_certificate(certificate_id: int, db: Session = Depends(get_db)) -> FileResponse:
    certificate = crud.get_certificate(db, certificate_id)
    if certificate is None:
        raise HTTPException(status_code=404, detail=f"Certificate {certificate_id} not found")

    if certificate.status != CertificateStatus.SUCCESS:
        raise HTTPException(
            status_code=409,
            detail=f"Certificate {certificate_id} is not available (status: {certificate.status})",
        )

    file_path = certificate_service.resolve_certificate_path(certificate.file_path)
    if file_path is None or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Certificate file not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"certificate_{certificate.id}.pdf",
    )
