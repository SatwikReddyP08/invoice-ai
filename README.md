# InVoice AI

**Intelligent Multi-Stage Invoice Processing, Historical Price Analysis & Audit Desk**

InVoice AI is a full-stack document intelligence application engineered for accounts payable, procurement, and financial audit teams. Rather than relying on unpredictable autonomous agents, InVoice AI operates as a **strictly bounded, fixed multi-stage pipeline** combining multi-modal document understanding, deterministic financial arithmetic, same-vendor historical baselines, evidence-based AI review, and a dedicated human review desk.

---

## Table of Contents

1. [Product Overview & Key Features](#1-product-overview--key-features)
2. [The Fixed Multi-Stage Pipeline](#2-the-fixed-multi-stage-pipeline)
3. [Architecture & Technology Stack](#3-architecture--technology-stack)
4. [Prerequisites & Environment Configuration](#4-prerequisites--environment-configuration)
5. [Local Setup & Startup Guide (Windows)](#5-local-setup--startup-guide-windows)
6. [Core API Endpoints Reference](#6-core-api-endpoints-reference)
7. [Focused Invoice Review Desk](#7-focused-invoice-review-desk)
8. [Research & Document AI Benchmarking](#8-research--document-ai-benchmarking)
9. [Security Considerations](#9-security-considerations)
10. [Manual Verification Walkthrough](#10-manual-verification-walkthrough)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Product Overview & Key Features

Accounts payable teams regularly process hundreds of supplier invoices, exposing organizations to costly operational risks:
1. **Mathematical Discrepancies**: Inconsistent line totals, incorrect tax computations, or subtotal mismatches.
2. **Unnoticed Price Creep**: Suppliers incrementally raising unit prices on recurring catalog products above historical contract rates.
3. **Duplicate Billing**: Inadvertent double-payment of previously submitted invoice numbers from the same vendor.

InVoice AI addresses these challenges through a unified, reproducible four-stage workflow:

* **Visual Document Understanding**: High-fidelity data extraction using Groq Cloud Vision (`qwen/qwen3.8-27b`) into a validated Pydantic schema, accurately handling rotated layouts, discounts, multi-page tables, and currencies.
* **Deterministic Financial Arithmetic**: Pure Python monetary math (`Decimal`) validating that line totals sum to subtotal and subtotal plus tax equals total amount, with zero reliance on LLMs for calculations.
* **Same-Vendor Historical Price Baselines**: Identifies previous invoices from the same vendor and strictly prior dates, evaluating current unit prices against historical averages with percentage variances and IQR outlier filtering.
* **Evidence-Based AI Review**: A dedicated second LLM pass that synthesizes verified arithmetic and historical findings into procurement explanations, operating under guardrails that neutralize unprovable fraud allegations.
* **Human Review Desk**: Triage queues (`Needs Attention`, `Completed Reviews`, `Informational / Normal`, `All Invoices`) enabling human reviewers to log formal dispositions (`ACKNOWLEDGED`, `NEEDS_FOLLOW_UP`, `RESOLVED`) and export comprehensive JSON audit reports.

---

## 2. The Fixed Multi-Stage Pipeline

InVoice AI enforces an architectural boundary: **AI models read documents and interpret evidence; deterministic Python code computes mathematics and validates business rules.**

```text
+---------------------------------------------------------------------------------+
|                                 INVOICE DOCUMENT                                |
|                                (PDF, PNG, JPEG)                                 |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                       STAGE 1: DOCUMENT UNDERSTANDING                           |
|  * Vision Model: Groq Cloud Vision API (qwen/qwen3.8-27b)                       |
|  * Multi-page base64 rendering via PyMuPDF                                     |
|  * Pydantic Schema Validation: Strict extraction of headers, line items & amounts|
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                  STAGE 2: DETERMINISTIC ANALYSIS (Zero AI)                      |
|  * Financial Validation: Decimal arithmetic verification (Qty * Price == Line,  |
|    Subtotal + Tax == Total, zero/negative value and missing field guards)       |
|  * Historical Analysis: Same-vendor normalized matching, duplicate invoice      |
|    exclusion, temporal filtering (date < current), unit-price change evaluation |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                     STAGE 3: EVIDENCE-BASED AI REVIEW                           |
|  * LLM Reviewer (Groq API): Interprets verified Stage 2 evidence findings.      |
|  * Post-Validation Guardrails: Neutralizes accusatory terminology, preserves    |
|    informational price decrease policy, enforces evidence fidelity.             |
|  Output: Review Status, Recommendation, Identifiable Findings & Explanation     |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                     STAGE 4: INVOICE REVIEW DESK (Human-in-the-Loop)            |
|  * Triage Queues: 'Needs Attention', 'Completed Reviews', 'Informational'       |
|  * Human Disposition: Record ACKNOWLEDGED, NEEDS_FOLLOW_UP, or RESOLVED         |
|  * Audit Export: Downloadable JSON audit report preserving all pipeline stages  |
+---------------------------------------------------------------------------------+
```

### Stage Responsibilities
| Stage | Engine | Responsibility |
|---|---|---|
| **Stage 1: Document Understanding** | Groq / Qwen Vision | Extracts vendor, customer, dates, currency, line items, and financial totals into a validated Pydantic schema. |
| **Stage 2: Deterministic Analysis** | Pure Python (`Decimal`) | Verifies internal arithmetic and compares current unit prices strictly against prior invoices from the same vendor. |
| **Stage 3: Evidence-Based AI Review** | Groq API + Guardrails | Synthesizes findings into explainable procurement notes without hallucinating facts or asserting fraud. |
| **Stage 4: Invoice Review Desk** | FastAPI + React UI | Allows human reviewers to triage exceptions, log dispositions with notes, and download comprehensive audit summaries. |

---

## 3. Architecture & Technology Stack

* **Backend**: Python 3.11+, FastAPI (REST API framework), SQLAlchemy 2.0 (ORM), Alembic (migrations), Pydantic v2 (validation), PyMuPDF (PDF image rasterization).
* **Frontend**: React 18, Vite (fast HMR dev server), Vanilla CSS (bespoke dark glassmorphism design system, responsive tables, zero Tailwind dependency).
* **Database**: PostgreSQL 14+ (relational storage with JSON document audit fields).
* **Cloud AI**: Groq Cloud SDK (`groq-python`) leveraging `qwen/qwen3.8-27b`.
* **Research Suite**: Isolated benchmark suite in `backend/evaluation/` comparing multi-modal vision LLMs against Document AI candidates.

---

## 4. Prerequisites & Environment Configuration

### Prerequisites
* **Python**: Version 3.11 or 3.12 (with `pip` and `venv`).
* **Node.js**: Version 18.x or 20.x (with `npm`).
* **PostgreSQL**: Version 14 or higher running on port 5432.
* **Groq API Key**: A valid API key from [Groq Cloud](https://console.groq.com/).

### Environment Variables (`backend/.env`)
Copy `backend/.env.example` to `backend/.env` and provide your credentials:

```ini
PROJECT_NAME="InVoice AI"
API_V1_STR="/api/v1"

# PostgreSQL Configuration
POSTGRES_SERVER=localhost
POSTGRES_USER=invoice_app
POSTGRES_PASSWORD=your_postgres_password_here
POSTGRES_DB=invoice_db
POSTGRES_PORT=5432

# Groq Vision API Configuration
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b

# Deterministic Analysis Policy Thresholds
PRICE_CHANGE_THRESHOLD_PERCENT=10.0
PRICE_CHANGE_MATERIAL_PERCENT=25.0
MONETARY_TOLERANCE=0.05
```

---

## 5. Local Setup & Startup Guide (Windows)

### Step 1: Clone Repository
```powershell
git clone https://github.com/your-username/invoice-ai.git
cd invoice-ai/InVoice
```

### Step 2: Configure PostgreSQL Database
In PostgreSQL (`psql` or pgAdmin), create the database user and database:
```sql
CREATE USER invoice_app WITH PASSWORD 'your_secure_password';
CREATE DATABASE invoice_db OWNER invoice_app;
GRANT ALL PRIVILEGES ON DATABASE invoice_db TO invoice_app;
```

### Step 3: Setup Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your PostgreSQL password and Groq API key
alembic upgrade head
```

### Step 4: Setup Frontend
In a separate terminal:
```powershell
cd frontend
npm install
```

### Step 5: Start Development Servers

* **Terminal 1 (Backend)**:
  ```powershell
  cd backend
  .\.venv\Scripts\Activate.ps1
  uvicorn app.main:app --reload --port 8000
  ```
  API Docs: `http://localhost:8000/docs`

* **Terminal 2 (Frontend)**:
  ```powershell
  cd frontend
  npm run dev
  ```
  Application UI: `http://localhost:5173`

---

## 6. Core API Endpoints Reference

All endpoints are prefixed with `/api/v1/invoices`:

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Uploads PDF, PNG, or JPEG invoice file and creates initial database record. |
| `POST` | `/{id}/extract` | Executes the complete multi-stage AI pipeline on the invoice. |
| `GET` | `/` | Queries invoices with queue filter (`all`, `needs_attention`, `completed`, `informational`). |
| `GET` | `/{id}` | Retrieves full invoice details, line items, financial validation, and AI review. |
| `POST` | `/{id}/disposition` | Records human reviewer decision (`ACKNOWLEDGED`, `NEEDS_FOLLOW_UP`, `RESOLVED`) and notes. |
| `GET` | `/{id}/report` | Generates a comprehensive JSON audit report for procurement compliance. |
| `DELETE` | `/{id}` | Deletes an invoice record and associated line items. |

For detailed endpoint documentation and schemas, refer to [`backend/README.md`](file:///f:/InVoice-20260927T141257Z-1-001/InVoice/backend/README.md) or visit the interactive Swagger UI at `http://localhost:8000/docs`.

---

## 7. Focused Invoice Review Desk

The Review Desk provides a clear triage workflow separating automated findings from human business judgments:

* **Needs Attention Queue**: Invoices flagged by the deterministic engine or AI review (e.g. arithmetic discrepancy, duplicate invoice submission, or material unit-price increase).
* **Completed Reviews Queue**: Invoices where an authorized reviewer has recorded a formal disposition.
* **Informational / Normal Queue**: Invoices verified mathematically consistent with no action required, or where price decreases are cataloged as informational per company policy.
* **All Invoices Queue**: Master ledger of all processed documents.

### Reviewer Dispositions
* `ACKNOWLEDGED`: Findings and minor variances noted; approved to proceed through standard AP workflow.
* `NEEDS_FOLLOW_UP`: Discrepancy or unapproved price increase flagged; requires clarification from supplier or procurement.
* `RESOLVED`: Exception investigated, verified (e.g. renewed annual master services agreement), and cleared.

---

## 8. Research & Document AI Benchmarking

In addition to the production application, InVoice AI includes a research suite benchmarking alternative document understanding models against ground-truth invoice datasets.

Candidate models evaluated include:
* **Groq / Qwen Vision (`qwen/qwen3.8-27b`)** *(Production Primary)*: 100% header field accuracy and 90% full table extraction on reference test set.
* **LayoutLMv3 (`layoutlmv3-finetuned-invoice`)**: Token-classification encoder; fragmented multi-line addresses and struggled with table column association.
* **Donut (`invoices-donut-model-v1`)**: OCR-free generative model; prone to line item count hallucinations and multi-page truncation.
* **PyMuPDF Deterministic Spatial Parser**: Rule-based coordinate clustering; ultra-fast (0.08s) on digital text, but unsupported on scanned raster images.

For full benchmarking methodology, quantitative metrics, and reproducible scripts, see [`backend/evaluation/README.md`](file:///f:/InVoice-20260927T141257Z-1-001/InVoice/backend/evaluation/README.md).

---

## 9. Security Considerations

* **MIME & Magic Byte Inspection**: Uploaded documents are verified using `filetype` binary magic byte inspection, rejecting renamed executable binaries or unauthorized formats.
* **Strict Size Bounds**: Uploads are restricted to a maximum of 10 MB per file.
* **Zero Credential Leakage**: Database passwords and API keys reside exclusively in local `.env` files and are excluded from git.
* **SQL Injection Prevention**: All queries utilize SQLAlchemy ORM parameterized statements.

---

## 10. Manual Verification Walkthrough

To verify the system end-to-end:

1. **Verify Services**: Ensure backend is running on `http://localhost:8000` and frontend on `http://localhost:5173`.
2. **Upload Invoice**:
   - On the **Upload & Process** screen, drag and drop an invoice PDF (e.g., an invoice from `Nova Workspace Solutions`).
   - Click **Upload Invoice**. Verify upload succeeds and displays the Invoice ID and filename.
3. **Execute AI Pipeline**:
   - Click **Process Invoice**.
   - Observe the step indicator transition through Document Understanding, Financial Analysis, and AI Invoice Review.
4. **Inspect Pipeline Results**:
   - Verify extracted vendor name, invoice number, date, and line items.
   - Inspect the **Financial Summary** to confirm arithmetic validation (Subtotal + Tax == Total).
   - Inspect the **Historical Price Context** to verify same-vendor prior invoice comparisons and percentage variances.
   - Review the **AI Invoice Review** findings and overall recommendation.
5. **Record Reviewer Disposition**:
   - Select disposition `RESOLVED` in the Human Review Desk section.
   - Enter justification note: `"Verified against contract renewal pricing"`.
   - Click **Record Human Disposition**. Verify the status updates to `Reviewer: RESOLVED`.
6. **Download Audit Report**:
   - Click **Download Audit Report (JSON)**.
   - Verify that the downloaded file contains the full record: extracted data, arithmetic proof, historical baseline comparisons, AI review findings, and recorded human disposition.
7. **Verify Review Desk Queue**:
   - Click **Invoice Review Desk** in the top navigation.
   - Verify the invoice appears in the **Completed Reviews** tab with disposition `RESOLVED`.

---

## 11. Troubleshooting

* **Backend 500 on Extraction (`GROQ_API_KEY is not configured`)**:
  Ensure `.env` exists in `backend/` and contains a valid `GROQ_API_KEY`.
* **Database Connection Refused (`connection to server at "localhost" failed`)**:
  Verify PostgreSQL service is active and listening on port 5432 (`pg_isready -p 5432`).
* **Frontend CORS or Proxy Errors**:
  Ensure the backend is running on port 8000 before initiating frontend requests. Vite proxies `/api` calls directly to `http://localhost:8000`.
* **Alembic Migration Error (`relation already exists`)**:
  If tables were created manually, stamp Alembic to head using `alembic stamp head`.
