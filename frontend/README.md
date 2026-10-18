# InVoice AI — Frontend Application

The frontend of InVoice AI is a modern, responsive single-page web application built with **React 18**, **Vite**, and **Vanilla CSS**. It provides an intuitive interface for uploading invoice documents, inspecting multi-stage pipeline results, triaging flagged discrepancies, and recording human audit decisions.

---

## Architecture & Component Hierarchy

```text
frontend/
├── src/
│   ├── assets/               # Static assets & icons
│   ├── components/
│   │   ├── UploadInvoice.jsx # Drag-and-drop file upload & trigger processing
│   │   ├── UploadInvoice.css
│   │   ├── InvoiceResults.jsx# Complete multi-stage result view & disposition recorder
│   │   ├── InvoiceResults.css
│   │   ├── ReviewDesk.jsx    # Triage queues (Needs Attention, Completed, Informational)
│   │   └── ReviewDesk.css
│   ├── App.jsx               # Header, top-level tabs & desk-to-detail navigation
│   ├── App.css               # Container layout & responsive wrappers
│   ├── index.css             # Dark-mode glassmorphic design system & typography
│   └── main.jsx              # React DOM root entrypoint
├── index.html                # HTML template (Google Fonts Outfit & Inter)
├── package.json              # React & Vite build dependencies
└── vite.config.js            # Development proxy to backend API (port 8000)
```

---

## User Workflow & Key Views

1. **Upload & Process (`UploadInvoice`)**:
   * Accepts PDF, PNG, and JPEG invoice documents up to 10MB.
   * Performs client-side type and size validation.
   * Uploads file to `/api/v1/invoices/upload`.
   * Upon successful staging, provides a single **"Process Invoice"** action to trigger the end-to-end pipeline.

2. **Pipeline Inspection (`InvoiceResults`)**:
   * **Stage 1 Indicator**: Shows Document Understanding status and extraction latency.
   * **Line Items Table**: Renders extracted descriptions, quantities, unit prices, tax rates, and line totals.
   * **Stage 2 Financial Summary**: Displays deterministic arithmetic validation (Subtotal + Tax == Total) and alerts for discrepancies.
   * **Historical Price Comparison**: Same-vendor baseline table comparing current unit prices to previous prices, historical averages, and sample size with percentage variance and outlier metrics.
   * **Stage 3 AI Review**: Synthesizes verified findings into clear recommendations (`REVIEW_RECOMMENDED`, `NO_ACTION_REQUIRED`, `INSUFFICIENT_DATA`) without accusatory language.
   * **Stage 4 Reviewer Action**: Dropdown to record reviewer disposition (`ACKNOWLEDGED`, `NEEDS_FOLLOW_UP`, `RESOLVED`) with optional justification notes.
   * **Audit Export**: Single-click download of the complete JSON audit report for procurement records.

3. **Invoice Review Desk (`ReviewDesk`)**:
   * Triage view categorizing all processed invoices into filtered tabs:
     * **Needs Attention**: Invoices flagged by the deterministic engine or AI review requiring human follow-up.
     * **Completed Reviews**: Invoices where human disposition has been formally recorded.
     * **Informational / Normal**: Invoices verified consistent with no action required.
     * **All Invoices**: Master overview of all documents in the system.
   * Provides quick links to inspect invoices or download audit reports directly from the queue.

---

## Getting Started

### Prerequisites
* **Node.js**: Version 18.x or 20.x
* **npm**: Version 9.x or higher

### Installation
```powershell
cd frontend
npm install
```

### Running the Development Server
```powershell
npm run dev
```

The frontend will start at:
```text
http://localhost:5173/
```

### API Proxy Configuration
During development, Vite automatically proxies `/api` requests to `http://localhost:8000` as defined in `vite.config.js`:
```javascript
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

---

## Production Build

To compile and bundle the static frontend assets for production deployment:
```powershell
npm run build
```
Production assets are output to the `frontend/dist/` directory.
