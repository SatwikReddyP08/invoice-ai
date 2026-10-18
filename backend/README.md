# InVoice AI — Backend Service

The backend of InVoice AI is a high-performance Python application built with **FastAPI**, **SQLAlchemy 2.0**, and **PostgreSQL**. It orchestrates a fixed, four-stage invoice intelligence pipeline combining vision-based document extraction, deterministic financial arithmetic, same-vendor historical price baselining, evidence-based AI review, and human triage logging.

---

## Architecture & Directory Layout

```text
backend/
├── alembic/                      # Database migration scripts
│   ├── env.py
│   └── versions/                 # Versioned migration files
├── alembic.ini                   # Alembic configuration
├── app/
│   ├── api/
│   │   ├── api.py                # Main API router registration
│   │   └── endpoints/
│   │       └── invoices.py       # Upload, extract, query, disposition & report endpoints
│   ├── core/
│   │   ├── config.py             # Pydantic BaseSettings & policy thresholds
│   │   └── database.py           # SQLAlchemy engine & session factory
│   ├── crud/
│   │   └── crud_invoice.py       # Filtered queries & transactional CRUD
│   ├── models/
│   │   ├── base.py               # DeclarativeBase class
│   │   └── invoice.py            # Invoice & InvoiceItem ORM models, PipelineStatus
│   ├── schemas/
│   │   ├── invoice.py            # Pydantic schemas for requests, responses & items
│   │   └── upload.py             # File upload schemas
│   ├── services/
│   │   ├── ai_extractor.py       # Stage 1: Groq / Qwen Vision extraction
│   │   ├── financial_analysis.py # Stage 2: Pure Python Decimal arithmetic validation
│   │   ├── historical_analysis.py# Stage 2: Same-vendor historical price baselines
│   │   ├── ai_review.py          # Stage 3: Evidence-based LLM review & guardrails
│   │   └── upload_service.py     # File storage & MIME-type validation
│   └── main.py                   # FastAPI application initialization & CORS
├── evaluation/                   # Isolated research & benchmark test suite
├── storage/                      # Uploaded invoice files (ignored by git)
├── requirements.txt              # Production Python dependencies
├── .env.example                  # Environment configuration template
└── run_e2e.py                    # End-to-end pipeline verification script
```

---

## Prerequisites

* **Python 3.11+** (3.11 or 3.12 recommended)
* **PostgreSQL 14+** running locally or in a container
* **Groq API Key** with access to vision models (e.g., `qwen/qwen3.8-27b`)

---

## Installation & Setup

1. **Create and activate a virtual environment**:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your database credentials and API key:
   ```powershell
   cp .env.example .env
   ```
   Key variables:
   * `POSTGRES_SERVER`: Hostname (default: `localhost`)
   * `POSTGRES_PORT`: Port (default: `5432`)
   * `POSTGRES_USER`: Database username
   * `POSTGRES_PASSWORD`: Database password
   * `POSTGRES_DB`: Database name (e.g., `invoice_db`)
   * `GROQ_API_KEY`: Your Groq Cloud API key
   * `GROQ_MODEL`: Vision extraction model (default: `qwen/qwen3.8-27b`)
   * `PRICE_CHANGE_THRESHOLD_PERCENT`: Threshold for flagging price increases (default: `10.0`)
   * `PRICE_CHANGE_MATERIAL_PERCENT`: Threshold for severe price increases (default: `25.0`)
   * `MONETARY_TOLERANCE`: Float rounding tolerance for arithmetic checks (default: `0.05`)

4. **Initialize Database Migrations**:
   Run Alembic to apply schema migrations:
   ```powershell
   alembic upgrade head
   ```

---

## Running the Backend

Start the development server with live reload:
```powershell
uvicorn app.main:app --reload --port 8000
```

The interactive OpenAPI documentation is available at:
* Swagger UI: `http://localhost:8000/docs`
* ReDoc: `http://localhost:8000/redoc`

---

## Core API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/invoices/upload` | Uploads PDF/PNG/JPEG document and creates pending DB record |
| `POST` | `/api/v1/invoices/{id}/extract` | Executes the complete multi-stage pipeline on the invoice |
| `GET` | `/api/v1/invoices/` | Lists invoices with review filter (`needs_attention`, `completed`, `informational`, `all`) |
| `GET` | `/api/v1/invoices/{id}` | Retrieves full invoice details, line items, and audit context |
| `POST` | `/api/v1/invoices/{id}/disposition` | Records a human reviewer decision (`ACKNOWLEDGED`, `NEEDS_FOLLOW_UP`, `RESOLVED`) |
| `GET` | `/api/v1/invoices/{id}/report` | Generates a standalone JSON audit report containing all stage proofs |
| `DELETE` | `/api/v1/invoices/{id}` | Deletes an invoice and its associated line items |

---

## Automated Verification Scripts

The backend includes test scripts to verify pipeline isolation and business logic:

* `test_adversarial_robustness.py`: Rigorous unit tests verifying Decimal monetary arithmetic, negative quantity guards, and historical price comparison edge cases.
* `test_robust_historical_analysis.py`: Verifies same-vendor matching, outlier filtering (IQR), and temporal filtering (strictly prior dates).
* `test_pipeline_separation.py`: Confirms that Stage 1, Stage 2, and Stage 3 maintain strict architectural boundaries without cross-stage contamination.
* `test_duplicate_extraction.py`: Validates that duplicate invoice submissions are detected and excluded from historical baselines.
* `run_e2e.py`: Uploads and processes an invoice through the end-to-end pipeline.
