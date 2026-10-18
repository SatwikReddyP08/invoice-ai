# InVoice AI

**Intelligent Invoice Extraction, Historical Price Analysis & Audit Desk**

InVoice AI is a full-stack document intelligence application engineered for accounts payable, procurement, and finance audit teams. Rather than relying on unpredictable autonomous agents, InVoice AI operates as a **strictly bounded, multi-stage pipeline** combining visual document understanding, deterministic financial arithmetic, historical same-vendor baselines, evidence-based AI review, and a dedicated human review desk.

---

## Table of Contents

1. [Product Purpose & Intended Users](#1-product-purpose--intended-users)
2. [The Fixed Multi-Stage Pipeline](#2-the-fixed-multi-stage-pipeline)
3. [Extraction Architectures (Selectable Modes)](#3-extraction-architectures-selectable-modes)
4. [Architecture & Technology Stack](#4-architecture--technology-stack)
5. [Local Setup Guide (Windows)](#5-local-setup-guide-windows)
6. [Environment Configuration (`.env.example`)](#6-environment-configuration-envexample)
7. [Application Startup & API Endpoints](#7-application-startup--api-endpoints)
8. [Focused Invoice Review Desk](#8-focused-invoice-review-desk)
9. [Limitations & Benchmark Honesty](#9-limitations--benchmark-honesty)
10. [Pipeline Run Success vs. Extraction Correctness](#10-pipeline-run-success-vs-extraction-correctness)
11. [Security Considerations & Future Roadmap](#11-security-considerations--future-roadmap)
12. [Manual Verification Walkthrough](#12-manual-verification-walkthrough)

---

## 1. Product Purpose & Intended Users

### Purpose
Accounts payable teams regularly process hundreds of supplier invoices, exposing organizations to three costly risks:
1. **Mathematical discrepancies** (unbalanced line totals, tax computation errors, or subtotal mismatches).
2. **Unnoticed price creep** (vendors raising unit prices on recurring products above agreed contract rates).
3. **Duplicate billing** (inadvertent double-payment of previously submitted invoice numbers).

InVoice AI addresses these challenges through automated extraction, deterministic validation, and explainable evidence-based findings before payment disbursement.

### Intended Users
- **Finance & Accounts Payable (AP) Specialists**: Review pending supplier invoices, audit line items against historical vendor averages, and log formal approval or exception dispositions.
- **Procurement & Vendor Managers**: Track unit price variances across recurring catalog items and detect unapproved price increases.
- **Financial Controllers & Auditors**: Export comprehensive audit logs containing extraction provenance, deterministic math checks, historical baselines, and recorded human reviewer notes.

---

## 2. The Fixed Multi-Stage Pipeline

InVoice AI enforces an architectural boundary: **AI models read documents and interpret evidence; deterministic Python code computes mathematics and validates rules.**

```
+---------------------------------------------------------------------------------+
|                                 INVOICE DOCUMENT                                |
|                                (PDF, PNG, JPEG)                                 |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                       STAGE 1: DOCUMENT UNDERSTANDING                           |
|  * Mode A: LLM-Assisted Vision (Groq / Qwen Vision qwen/qwen3.8-27b)            |
|  * Mode B: Non-LLM Deterministic Parser (PyMuPDF Layout & Coordinate Clustering)|
|  Output: Structured Invoice Schema (Headers, Line Items, Amounts, Currency)     |
+---------------------------------------------------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
|                  STAGE 2: DETERMINISTIC ANALYSIS (Zero AI)                      |
|  * Financial Validation: Decimal arithmetic verification (Qty * Price == Total, |
|    Subtotal + Tax == Grand Total, zero/negative value detection)                |
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
|  * Audit Export: Downloadable JSON/Audit Report preserving all pipeline stages  |
+---------------------------------------------------------------------------------+
```

### Stage Responsibilities
| Stage | Engine | Responsibility |
|---|---|---|
| **Stage 1: Document Understanding** | Groq / Qwen Vision or PyMuPDF | Extracts vendor, customer, dates, currency, line items, and financial totals into a validated Pydantic schema. |
| **Stage 2: Deterministic Analysis** | Pure Python (`Decimal`) | Verifies internal arithmetic and compares current unit prices strictly against prior invoices from the same vendor. |
| **Stage 3: Evidence-Based AI Review** | Groq API + Post-Validation Guardrails | Synthesizes findings into human-understandable procurement explanations without hallucinating facts or asserting fraud. |
| **Stage 4: Invoice Review Desk** | FastAPI + React UI | Allows human reviewers to triage exceptions, log dispositions with notes, and download comprehensive audit summaries. |

---

## 3. Extraction Architectures (Selectable Modes)

InVoice AI provides three selectable extraction modes to accommodate operational preferences:

### 1. LLM-Assisted Extraction (Production Primary)
- **Model**: `qwen/qwen3.8-27b` via Groq Cloud Vision API.
- **Capabilities**: Robust multi-modal understanding handling complex digital layouts, rotated text, non-standard column grids, and raster scans.
- **Use Case**: Primary choice for unstructured, multi-format, or complex vendor invoices.

### 2. Non-LLM Deterministic Parser (Experimental Local)
- **Engine**: PyMuPDF (`fitz`) layout analysis and spatial word coordinate clustering.
- **Capabilities**: Zero API cost, completely local execution, deterministic coordinate-based table reconstruction, wrapped multi-line cell merging, and Indian GST vs. GSTIN identification.
- **Requirement**: Requires digital embedded text. Scanned raster PDFs without OCR return an explicit partial/unsupported status.

### 3. Side-by-Side Comparison Mode (Audit & Evaluation)
- **Engine**: Executes both LLM-assisted and Non-LLM extractions on the identical document in isolation.
- **Capabilities**: Inspects field-by-field header consensus, row-by-row line item alignment, and mathematical reconciliation side-by-side.
- **Isolation**: Runs strictly in memory and does not alter database baselines or generate duplicate history.

---

## 4. Architecture & Technology Stack

- **Backend**: Python 3.11+, FastAPI (REST API framework), SQLAlchemy 2.0 (ORM), Alembic (database migrations), Pydantic v2 (schema validation).
- **Frontend**: React 18, Vite (fast HMR dev server), Vanilla CSS (bespoke dark glassmorphism design system, responsive tables, zero Tailwind dependency).
- **Database**: PostgreSQL 14+ (relational storage with JSON/JSONB document audit fields).
- **Document Processing**: PyMuPDF (`fitz`) for PDF parsing, text coordinate grouping, table detection, and multi-page rendering.
- **Cloud AI**: Groq Cloud SDK (`groq-python`) leveraging `qwen/qwen3.8-27b`.

---

## 5. Local Setup Guide (Windows)

### Prerequisites
- **Python**: Version 3.11 or 3.12 (with `pip` and `venv`).
- **Node.js**: Version 18.x or 20.x (with `npm`).
- **PostgreSQL**: Version 14 or higher running locally on port 5432.
- **Groq API Key**: A free or paid API key from [Groq Cloud](https://console.groq.com/).

### Step 1: Clone Repository
```powershell
git clone https://github.com/your-username/invoice-ai.git
cd invoice-ai/InVoice
```

### Step 2: Setup Python Virtual Environment (Backend)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: Configure PostgreSQL Database
In PostgreSQL (`psql` or pgAdmin), create the database user and database:
```sql
CREATE USER invoice_app WITH PASSWORD 'your_secure_password';
CREATE DATABASE invoice_db OWNER invoice_app;
GRANT ALL PRIVILEGES ON DATABASE invoice_db TO invoice_app;
```

### Step 4: Configure Backend Environment Variables
Copy `.env.example` to `.env` and fill in your credentials:
```powershell
Copy-Item .env.example .env
notepad .env
```
Ensure `POSTGRES_PASSWORD` and `GROQ_API_KEY` are provided.

### Step 5: Run Database Migrations
Initialize database tables using Alembic:
```powershell
alembic upgrade head
```
*(Note: To add dedicated Review Desk columns, see the migration section below).*

### Step 6: Setup Frontend (React + Vite)
In a separate terminal:
```powershell
cd ..\frontend
npm install
```

---

## 6. Environment Configuration (`.env.example`)

The backend reads configuration from `backend/.env`. Placeholders are documented below:

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

## 7. Application Startup & API Endpoints

### Starting the Backend Server
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://localhost:8000`
- Swagger Interactive Documentation: `http://localhost:8000/docs`
- ReDoc Documentation: `http://localhost:8000/redoc`

### Starting the Frontend Client
```powershell
cd frontend
npm run dev
```
- Frontend Application URL: `http://localhost:5173`

### Key API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/invoices/upload` | Upload invoice document (PDF, PNG, JPEG) and create initial DB record. |
| `POST` | `/api/v1/invoices/{id}/extract?mode=llm\|non_llm` | Execute Stage 1 extraction, Stage 2 analysis, and Stage 3 AI review. |
| `POST` | `/api/v1/invoices/{id}/compare` | Run side-by-side comparison of LLM vs Non-LLM extraction in memory. |
| `GET` | `/api/v1/invoices/?review_filter={filter}` | Query invoices with queue filtering (`all`, `needs_attention`, `completed`, `informational`). |
| `POST` | `/api/v1/invoices/{id}/disposition` | Record human reviewer disposition (`ACKNOWLEDGED`, `NEEDS_FOLLOW_UP`, `RESOLVED`) and notes. |
| `GET` | `/api/v1/invoices/{id}/report` | Generate downloadable comprehensive audit report JSON. |
| `GET` | `/api/v1/invoices/{id}` | Retrieve invoice details, items, validation, and AI review. |

---

## 8. Focused Invoice Review Desk

The Review Desk provides a clear human-in-the-loop workflow separating machine evidence from human business judgments.

### Queue States
- **Needs Attention**: Invoices where Stage 3 recommended review (due to arithmetic discrepancies, duplicates, or significant price increases) that have not yet been resolved.
- **Completed Reviews**: Invoices where a human reviewer has recorded a formal disposition.
- **Informational / Normal**: Invoices passing all mathematical and historical checks, or where price decreases are cataloged as informational per company policy.

### Reviewer Dispositions
- `ACKNOWLEDGED`: Findings and minor variances noted; approved to proceed through standard processing.
- `NEEDS_FOLLOW_UP`: Discrepancy or unapproved price increase flagged; requires clarification from supplier or procurement.
- `RESOLVED`: Exception investigated, justified (e.g. renewed annual contract), and approved.

### Database Migration Notice
Reviewer dispositions are persisted inside `Invoice.review_result["human_disposition"]` JSON by default, enabling zero-downtime execution without mandatory schema migrations. An optional migration script (`c57d8123ef01_add_review_desk_columns.py`) is provided in `backend/alembic/versions/` for teams requiring dedicated SQL columns.
To execute the optional migration manually:
```powershell
cd backend
alembic upgrade head
```

---

## 9. Limitations & Benchmark Honesty

### Non-LLM Parser Boundaries
1. **Digital Text Only**: The Non-LLM extractor requires embedded vector/digital text. Scanned raster images or photocopies without embedded OCR text are detected and flagged as `FAILED_OR_UNSUPPORTED`.
2. **Layout Variations**: Heavily nested tables, unbordered multi-column layouts, or non-standard currency placements may yield partial extraction, flagged with `NEEDS_VERIFICATION`.
3. **No Silent Fabrication**: If a field cannot be deterministically validated, it is left `null` and flagged rather than fabricated.

### Single-Document Benchmark Honesty
- **Latency Ratio**: The relative speedup reported in Comparison Mode reflects **latency for that specific document only**. It does not constitute a generalized statistical benchmark.
- **Consensus vs. Accuracy**: Field agreement between LLM and Non-LLM extraction indicates algorithmic consensus on that document, but **does not prove factual correctness** without comparison against manually verified ground truth.

---

## 10. Pipeline Run Success vs. Extraction Correctness

A fundamental tenet of InVoice AI is distinguishing between **system execution status** and **data extraction accuracy**:

- **Execution Success (`pipeline_status == SUCCESS`)**: Indicates that the PDF was read, schemas were validated, deterministic math completed without unhandled exceptions, and the AI review completed.
- **Data Correctness**: Validated only when arithmetic reconciles (`Subtotal + Tax == Total`, `Qty * UnitPrice == LineTotal`), line items are fully parsed, and required anchors are present.

When an extraction succeeds at the system level but has missing fields or unverified totals, InVoice AI categorizes it with completeness status `NEEDS_VERIFICATION` and identifies the specific fields requiring human audit.

---

## 11. Security Considerations & Future Roadmap

### Security Best Practices
- **MIME & Magic Byte Verification**: Uploads are validated using `filetype` magic byte inspection, rejecting renamed executable binaries or unauthorized formats.
- **Size Enforced**: Uploads strictly limited to 10 MB per file.
- **Zero API Key Leakage**: API credentials and database passwords exist exclusively in `.env` and are strictly excluded via `.gitignore`.
- **SQL Injection Prevention**: All queries utilize SQLAlchemy ORM parameterized statements.

### Roadmap
- [ ] Local OCR fallback (Tesseract/PaddleOCR) for scanned PDFs in Non-LLM mode.
- [ ] Multi-tier approval workflows with role-based access control (RBAC).
- [ ] Direct ERP integration export (SAP S/4HANA, NetSuite, QuickBooks Online).
- [ ] Automated purchase order (PO) three-way matching.

---

## 12. Manual Verification Walkthrough

Follow these exact steps to verify the system manually:

1. **Verify Backend Status**:
   Start backend (`uvicorn app.main:app --reload`) and verify `http://localhost:8000/docs` loads.
2. **Verify Frontend Status**:
   Start frontend (`npm run dev`) and open `http://localhost:5173`.
3. **Test Non-LLM GST & Table Extraction (`ACD-2026-001`)**:
   - Upload invoice `ACD-2026-001` (Apex Cloud Dynamics Ltd).
   - Select **Non-LLM Deterministic Parser (Experimental Local)**.
   - Click **Process Invoice**.
   - Verify extracted values:
     - Customer: `InVoice Test Corp` (extracted from Billed-To section).
     - Subtotal: `₹20,000.00`.
     - Tax (GST 18%): `₹3,600.00` (strictly separated from GSTIN digits).
     - Total: `₹23,600.00`.
     - Line Items: 2 items extracted with quantities, prices, and totals.
4. **Test Side-by-Side Comparison**:
   - Upload the same invoice and select **Side-by-Side Comparison**.
   - Verify the Ground Truth notice banner is displayed.
   - Verify speedup is labeled as a current-document measurement.
   - Verify line-item and header agreement metrics are visible.
5. **Test Review Desk & Disposition**:
   - Navigate to **Invoice Review Desk** via top navigation.
   - Filter by **Needs Attention** and click on an invoice.
   - Record disposition `RESOLVED` with note `"Approved per annual IT budget renewal"`.
   - Click **Record Human Disposition** and verify the badge updates.
   - Click **Download Audit Report (JSON)** and confirm the downloaded report contains extraction provenance, deterministic math checks, historical baselines, and your human reviewer notes.
