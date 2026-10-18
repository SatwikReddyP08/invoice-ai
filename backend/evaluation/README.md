# Stage 1 Document AI Evaluation & Benchmarking

This directory contains the isolated research, evaluation datasets, ground-truth annotations, and benchmarking scripts created to evaluate alternative Stage 1 document understanding candidates for InVoice AI.

---

## 1. Objective & Evaluation Question

The primary research question investigated was:
> *"Can a specialized pretrained Document AI model (such as LayoutLMv3 or Donut) or a deterministic spatial layout parser reliably replace or supplement the multi-modal Vision LLM for Stage 1 invoice extraction?"*

To maintain engineering discipline, this evaluation was conducted using a standardized reference dataset with ground-truth labels and reproducible evaluation scripts.

---

## 2. Evaluation Dataset & Methodology

### Dataset Composition
The reference dataset (`evaluation/dataset/`) consists of 10 representative commercial invoice documents spanning diverse operational scenarios:
* **Digital Vector PDFs**: Clean single-page and multi-page invoices generated from standard billing systems.
* **Complex Multi-Item Tables**: Invoices with multiple line items, quantity discounts, and itemized tax breakdowns.
* **Non-Standard Currencies**: Invoices in USD ($), EUR (€), and INR (₹) with regional tax labels (VAT, IGST, GST).
* **Scanned Raster PDFs**: Document images embedded without native text layers.

### Evaluation Metrics
Each candidate model was benchmarked against verified ground truth across:
1. **Header Field Accuracy**: Exact match and normalized agreement across 8 key fields (`invoice_number`, `invoice_date`, `vendor_name`, `customer_name`, `subtotal`, `tax_amount`, `total_amount`, `currency`).
2. **Line Item Extraction**: Accurate extraction of description, quantity, unit price, and line total.
3. **Mathematical Balance**: Verification of arithmetic reconciliation (`Subtotal + Tax == Total` and `Quantity * Unit Price == Line Total`).
4. **Latency & Compute**: Execution time per document and hardware requirements.

---

## 3. Benchmarked Candidates & Results Summary (10-Document Reference Set)

> **Notice on Dataset Scope & Licensing:**
> The evaluation metrics below reflect an exploratory benchmark on a 10-document reference set created to evaluate architectural trade-offs. The raw external dataset file (`katanaml_test.parquet`) used during local experimentation has been excluded from public release due to unverified redistribution licensing. The benchmark scripts, procedural dataset generator (`prepare_evaluation_dataset.py`), and committed evaluation summaries in `results/` are preserved for research transparency.

| Model / Candidate | Architecture | Header Field Match (10 Docs) | Complete Table Extraction | Latency (Avg) | Assessment |
|---|---|---|---|---|---|
| **Groq / Qwen Vision (`qwen/qwen3.8-27b`)** | Multi-Modal Vision LLM | 80/80 fields (100%) | 9/10 tables (90%) | ~1.7s | **Primary Pipeline Baseline** |
| **LayoutLMv3 (`layoutlmv3-finetuned-invoice`)** | Transformer (BIO Token Classification) | 39/80 fields (48.7%) | 3/10 tables (30%) | ~0.6s | Experimental (token fragmentation) |
| **Donut (`invoices-donut-model-v1`)** | OCR-Free Vision Encoder-Decoder | 30/80 fields (37.5%) | 2/10 tables (20%) | ~2.1s | Generative hallucination & truncation |
| **PyMuPDF Spatial Parser** | Spatial Geometry & Coordinate Clustering | 57/80 fields (71.2%) | 6/10 tables (60%) | **0.08s** | Fast on clean digital PDFs; unsupported on scanned raster |

---

## 4. Key Findings & Engineering Limitations

### Why Vision LLM Was Chosen as the Pipeline Baseline
1. **Layout Invariance**: Multi-modal vision models interpret non-standard grids, rotated stamps, discounts, and regional tax notations without requiring per-vendor templates.
2. **Mathematical Consistency**: Vision LLMs reliably differentiate between item subtotal and grand total, preventing false arithmetic discrepancies in Stage 2.
3. **Scanned Document Handling**: Visual perception operates natively on raster images without external OCR engines.

### Deficiencies in Specialized Small Models
1. **Token Classification (LayoutLMv3)**: Highly susceptible to token fragmentation. While it identifies text as an "amount," it struggles to associate which amount corresponds to subtotal vs. tax vs. total in multi-column layouts.
2. **Generative Seq2Seq (Donut)**: Prone to generative hallucinations, skipping line items on long tables, and truncation on multi-page invoices.
3. **Deterministic Spatial Parsing**: Fast on digital invoices, but fails on raster images and breaks when column headers deviate from expected keywords.

### Evaluation Scope Notice
These metrics reflect performance solely on the 10-document reference set. They demonstrate architectural trade-offs on complex layouts and should not be interpreted as a blanket guarantee across all arbitrary global invoice formats.

---

## 5. Directory Structure & Benchmark Scripts

```text
evaluation/
├── dataset/
│   ├── ground_truth/         # Field-level JSON ground truth per document
│   └── invoices/             # 10 test invoice files (PDFs and PNGs)
├── data/
│   └── katanaml_test.parquet # Reference evaluation dataset
├── results/                  # Serialized evaluation outputs
│   ├── baseline_groq_qwen_results.json
│   ├── baseline_summary.json
│   ├── candidate_comparison_summary.json
│   ├── layoutlmv3_evaluation_results.json
│   ├── donut_evaluation_results.json
│   └── improved_document_ai_results.json
├── eval_stage1_document_ai.py          # Benchmark runner for Stage 1 baseline
├── eval_candidates_comparison.py       # Comparative scoring across candidates
├── eval_improved_document_extractor.py # Standalone spatial & layout parser test
└── prepare_evaluation_dataset.py       # Dataset curation and ground-truth generation
```

---

## 6. How to Reproduce Benchmarks

To run the comparative candidate evaluation:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python evaluation/eval_candidates_comparison.py
```

To run the standalone spatial parser evaluation:
```powershell
python evaluation/eval_improved_document_extractor.py
```
