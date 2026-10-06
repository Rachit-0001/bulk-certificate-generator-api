"""Certificate generation (ReportLab) and the background job processor.

Nothing in this file knows about HTTP routes. That keeps it easy to test.
"""
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app import crud, database
from app.models import Certificate, GenerationJob

logger = logging.getLogger(__name__)

# generated/ lives at the project root (two folders above app/services/)
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated"
ORGANIZATION_NAME = "Example Learning Academy"

NAVY = HexColor("#1F3A5F")
GOLD = HexColor("#B8860B")
GREY = HexColor("#555555")


# ----------------------------------------------------------------------------
# PDF generation
# ----------------------------------------------------------------------------
def _fit_font_size(text: str, font: str, max_size: int, max_width: float, min_size: int = 10) -> int:
    """Shrink the font until the text fits on the page, so long names don't overflow."""
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _draw_centered(pdf: canvas.Canvas, text: str, y: float, font: str, size: int, color=NAVY) -> None:
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    pdf.drawCentredString(pdf._pagesize[0] / 2, y, text)


def _draw_border(pdf: canvas.Canvas, width: float, height: float) -> None:
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(4)
    pdf.rect(25, 25, width - 50, height - 50)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.rect(36, 36, width - 72, height - 72)


def generate_certificate(
    output_path: Path,
    recipient_name: str,
    event_name: str,
    certificate_title: str,
    issue_date: date,
    certificate_code: Optional[str] = None,
) -> Path:
    """Create one certificate PDF at output_path and return that path.

    The layout (the "template") is drawn in code so there is no template
    file to edit or lose. Raises an exception if anything goes wrong; the
    caller decides what to do with the failure.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A4)
    max_text_width = width - 150

    try:
        # pageCompression=0 keeps the PDF text readable as plain bytes,
        # which lets the tests check that the recipient name is really in the file.
        pdf = canvas.Canvas(str(output_path), pagesize=(width, height), pageCompression=0)
        pdf.setTitle(f"{certificate_title} - {recipient_name}")
        _draw_border(pdf, width, height)

        _draw_centered(pdf, ORGANIZATION_NAME.upper(), height - 95, "Helvetica-Bold", 14, GOLD)

        title_text = certificate_title.upper()
        title_size = _fit_font_size(title_text, "Helvetica-Bold", 38, max_text_width, 18)
        _draw_centered(pdf, title_text, height - 150, "Helvetica-Bold", title_size)

        _draw_centered(pdf, "This is to certify that", height - 210, "Helvetica-Oblique", 16, GREY)

        name_size = _fit_font_size(recipient_name, "Helvetica-Bold", 36, max_text_width)
        _draw_centered(pdf, recipient_name, height - 265, "Helvetica-Bold", name_size)
        pdf.setStrokeColor(GOLD)
        pdf.setLineWidth(1)
        pdf.line(width / 2 - 200, height - 278, width / 2 + 200, height - 278)

        _draw_centered(pdf, "has successfully completed", height - 315, "Helvetica-Oblique", 16, GREY)

        event_size = _fit_font_size(event_name, "Helvetica-Bold", 26, max_text_width)
        _draw_centered(pdf, event_name, height - 355, "Helvetica-Bold", event_size)

        _draw_centered(pdf, f"Date: {issue_date.strftime('%d %b %Y')}", 110, "Helvetica", 14, GREY)
        if certificate_code:
            _draw_centered(pdf, f"Certificate ID: {certificate_code}", 85, "Helvetica", 11, GREY)

        pdf.showPage()
        pdf.save()
    except Exception:
        output_path.unlink(missing_ok=True)  # don't leave a half-written file behind
        raise
    return output_path


# ----------------------------------------------------------------------------
# Download helper
# ----------------------------------------------------------------------------
def resolve_certificate_path(relative_path: Optional[str]) -> Optional[Path]:
    """Turn the stored relative path into a real path, but only inside generated/.

    Returns None for anything that points outside OUTPUT_DIR, so a tampered
    database value can never be used to read arbitrary files.
    """
    if not relative_path:
        return None
    base = OUTPUT_DIR.resolve()
    candidate = (base / relative_path).resolve()
    if not candidate.is_relative_to(base):
        return None
    return candidate


# ----------------------------------------------------------------------------
# Background processing
# ----------------------------------------------------------------------------
def build_certificate_code(job_id: str, certificate_id: int) -> str:
    return f"{job_id[:8].upper()}-{certificate_id:05d}"


def _process_certificate(db, job: GenerationJob, certificate: Certificate) -> None:
    """Generate ONE certificate. Any error here only affects this certificate."""
    relative_path = f"{job.id}/{certificate.id}.pdf"
    try:
        generate_certificate(
            output_path=OUTPUT_DIR / relative_path,
            recipient_name=certificate.recipient_name,
            event_name=job.event_name,
            certificate_title=certificate.certificate_title,
            issue_date=job.issue_date,
            certificate_code=build_certificate_code(job.id, certificate.id),
        )
    except Exception as error:  # noqa: BLE001 - we deliberately catch everything here
        logger.warning("Certificate %s failed: %s", certificate.id, error)
        crud.mark_certificate_failed(db, job, certificate, f"Certificate generation failed: {error}")
        return
    crud.mark_certificate_success(db, job, certificate, relative_path)


def process_job(job_id: str) -> None:
    """Background task: process every certificate of a job, one by one.

    It opens its own database session because the request's session is
    closed by the time this runs.
    """
    db = database.SessionLocal()
    try:
        job = crud.get_job(db, job_id)
        if job is None:
            return
        crud.mark_job_processing(db, job)
        for certificate in list(job.certificates):
            _process_certificate(db, job, certificate)
        crud.finish_job(db, job)
    except Exception:  # noqa: BLE001 - something broke the whole job, not one certificate
        logger.exception("Job %s failed", job_id)
        db.rollback()
        crud.mark_job_failed(db, job_id)
    finally:
        db.close()
