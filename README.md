# Bulk Certificate Generator API

## Overview

A small backend API that generates PDF certificates in bulk. A client sends one request containing an event name and a list of recipients. The API validates the data, creates a **job**, answers immediately with a job ID, and generates one PDF per recipient **in the background**. The client can then check the job's progress, see which certificates succeeded or failed, and download each PDF.

## Features

- Bulk certificate generation (up to 1000 recipients per request)
- Request validation (Pydantic), including whitespace cleanup and duplicate-email detection
- Background processing with FastAPI `BackgroundTasks`
- Job progress tracking (`PENDING`, `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`)
- Individual failure handling: one bad recipient never stops the others
- PDF certificate generation with ReportLab (one predefined design)
- Certificate download as `application/pdf`
- SQLite database
- Automated tests (pytest, 35 tests, separate test database)
- Swagger / ReDoc API documentation

## Tech Stack

Python 3.11+, FastAPI, SQLite, SQLAlchemy, Pydantic, ReportLab, Pytest (with `httpx`, which FastAPI's `TestClient` needs), Uvicorn.

## Project Structure

```
bulk-certificate-generator/
├── app/
│   ├── main.py                      # Creates the FastAPI app, tables, 500 error handler
│   ├── database.py                  # SQLite engine, session factory, get_db dependency
│   ├── models.py                    # SQLAlchemy tables: GenerationJob, Certificate
│   ├── schemas.py                   # Pydantic request/response models + validation
│   ├── crud.py                      # All database reads/writes
│   ├── routers/certificates.py      # The 4 API endpoints (thin: validate, call, return)
│   └── services/certificate_service.py  # PDF generation + background job processor
├── generated/                       # PDFs are saved here (<job_id>/<certificate_id>.pdf)
├── tests/                           # pytest tests + fixtures (conftest.py)
├── requirements.txt
├── run.py                           # Optional launcher: python run.py
└── README.md / INTERVIEW_GUIDE.md
```

The certificate **layout (template) is drawn in code** inside `certificate_service.py` instead of being a separate PDF file. This keeps the project to one dependency for PDFs and nothing extra to load or merge.

## Setup

Requires Python 3.11 or newer.

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

Linux / Mac:

```bash
source venv/bin/activate
```

Install:

```bash
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

(or `python run.py`)

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

The SQLite file `certificates.db` is created automatically in the project folder on first start.

## Run Tests

```bash
pytest
```

Tests use a temporary SQLite database and a temporary output folder, so your real `certificates.db` and `generated/` folder are never touched. You may see one deprecation warning about `httpx` from Starlette's test client; it is harmless.

## API Usage

### 1. Create a generation job

`POST /api/v1/certificates/generate` → **202 Accepted**

```json
{
  "event_name": "Python Programming Workshop",
  "certificate_title": "Certificate of Completion",
  "issue_date": "2026-10-07",
  "recipients": [
    { "name": "Rachit Gangwar", "email": "rachit@example.com" },
    { "name": "Aman Kumar", "email": "aman@example.com" }
  ]
}
```

Response:

```json
{
  "job_id": "c5b4036c-d6ea-46a7-b884-8a8c6fca705b",
  "status": "PENDING",
  "total_count": 2,
  "message": "Certificate generation started"
}
```

Validation rules: at least 1 recipient; `name` and `email` required; email must look like `name@domain.tld`; whitespace is trimmed; emails are lowercased; duplicate emails in one request are rejected; `certificate_title` defaults to "Certificate of Completion". Bad input returns **422** with a clear message.

### 2. Check job status

`GET /api/v1/certificates/jobs/{job_id}` → 200 (or 404 if the job does not exist)

```json
{
  "job_id": "c5b4036c-d6ea-46a7-b884-8a8c6fca705b",
  "status": "PROCESSING",
  "total_count": 10,
  "successful_count": 6,
  "failed_count": 1,
  "pending_count": 3,
  "created_at": "2026-10-07T10:15:00.123456",
  "completed_at": null
}
```

`pending_count = total_count - successful_count - failed_count`

### 3. Get per-certificate results

`GET /api/v1/certificates/jobs/{job_id}/results` → 200 (or 404)

```json
{
  "job_id": "c5b4036c-d6ea-46a7-b884-8a8c6fca705b",
  "certificates": [
    {
      "certificate_id": 1,
      "recipient_name": "Rachit Gangwar",
      "email": "rachit@example.com",
      "status": "SUCCESS",
      "download_url": "/api/v1/certificates/1/download",
      "error_message": null
    },
    {
      "certificate_id": 2,
      "recipient_name": "Aman Kumar",
      "email": "aman@example.com",
      "status": "FAILED",
      "download_url": null,
      "error_message": "Certificate generation failed: <reason>"
    }
  ]
}
```

### 4. Download a certificate

`GET /api/v1/certificates/{certificate_id}/download`

- **200** – the PDF (`application/pdf`)
- **404** – certificate (or its file) does not exist
- **409** – certificate exists but is not available (status `FAILED` or `PENDING`)

### Try it from the command line

```bash
curl -X POST http://127.0.0.1:8000/api/v1/certificates/generate \
  -H "Content-Type: application/json" \
  -d '{"event_name":"Python Workshop","issue_date":"2026-10-07","recipients":[{"name":"Rachit Gangwar","email":"rachit@example.com"}]}'

curl http://127.0.0.1:8000/api/v1/certificates/jobs/<job_id>
curl -o certificate.pdf http://127.0.0.1:8000/api/v1/certificates/1/download
```

## Job Status Rules

| Situation | Job status |
|---|---|
| Created, waiting for background task | `PENDING` |
| Background task is working | `PROCESSING` |
| Every certificate succeeded | `COMPLETED` |
| At least one certificate failed, but the job ran to the end | `COMPLETED_WITH_ERRORS` |
| The job as a whole could not run (e.g. database error) | `FAILED` |

If **every** certificate fails, the job is still `COMPLETED_WITH_ERRORS` (the job itself ran fine; every failure is listed in `/results`). `FAILED` is reserved for whole-job problems.

## Design Decisions

### Why FastAPI?
Simple REST API development, automatic request validation, automatic Swagger documentation, and good Python support (type hints).

### Why SQLite?
The assignment only requires a relational database, and SQLite keeps local setup simple: no server to install, just a file.

### Why BackgroundTasks?
Bulk certificate generation can take time, so the API returns immediately with a job ID while generation happens in the background. The client polls the status endpoint.

### Why process each certificate independently?
One bad recipient should not stop valid recipients from being processed. Each certificate is wrapped in its own `try/except`, and its result is saved to the database right away.

### Why ReportLab?
It provides a simple way to generate PDF certificates programmatically without requiring an external service.

## Limitations of BackgroundTasks

`BackgroundTasks` runs inside the same process as the API. That is perfect for this assignment, but it has limits:

- **Not durable:** if the server restarts while a job is running, the job stays stuck in `PROCESSING` and is not resumed.
- **No retries, no scheduling, no priorities.**
- **Shares the server's resources:** a huge job competes with API requests for CPU.
- **Cannot scale across several servers:** the task lives only in the process that received the request.

This is why the request size is capped at 1000 recipients. A production system with very large workloads would use a dedicated task queue (for example Celery with Redis) and separate worker processes. That is deliberately **not** implemented here to keep the project simple.

## Known Limitations

- ReportLab's built-in fonts only support Latin characters. Names in other scripts (e.g. Devanagari) appear as solid black boxes in the PDF; supporting them needs a TTF font that contains those glyphs.
- There is no authentication (not required by the assignment).
- SQLite is fine for local use, but not for heavy concurrent writes.
