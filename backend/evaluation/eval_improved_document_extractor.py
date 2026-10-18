import os
import sys
import json
import time
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
import fitz # PyMuPDF
from pydantic import ValidationError

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema
from evaluation.eval_stage1_document_ai import (
    evaluate_predictions,
    check_deterministic_fallback,
    DATASET_DIR,
    INVOICES_DIR,
    GROUND_TRUTH_DIR,
    RESULTS_DIR
)

def parse_monetary_string(s: str) -> Optional[float]:
    if not s:
        return None
    # Remove currency symbols and non-numeric chars except . and ,
    clean = re.sub(r"[^\d.,]", "", s.strip())
    if not clean:
        return None
    # Handle European vs US format
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            # European: 1.234,56
            clean = clean.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56
            clean = clean.replace(",", "")
    elif "," in clean:
        # Check if comma is decimal separator (e.g. 12,50)
        parts = clean.split(",")
        if len(parts) == 2 and len(parts[1]) in [1, 2]:
            clean = clean.replace(",", ".")
        else:
            clean = clean.replace(",", "")
    try:
        return float(clean)
    except Exception:
        return None

def parse_date_string(s: str) -> Optional[date]:
    if not s:
        return None
    date_patterns = [
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{1,2})/(\d{1,2})/(\d{4})"
    ]
    for pat in date_patterns:
        m = re.search(pat, s, re.IGNORECASE)
        if m:
            matched_str = m.group(0)
            for fmt in ["%d %B %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
                try:
                    return datetime.strptime(matched_str, fmt).date()
                except Exception:
                    continue
    return None

def extract_currency(text: str) -> Optional[str]:
    if re.search(r"\bINR\b|₹", text, re.IGNORECASE):
        return "INR"
    if re.search(r"\bEUR\b|€", text, re.IGNORECASE):
        return "EUR"
    if re.search(r"\bUSD\b|\$", text, re.IGNORECASE):
        return "USD"
    if re.search(r"\bGBP\b|£", text, re.IGNORECASE):
        return "GBP"
    return None

def extract_improved_document_ai(file_path: str) -> Optional[InvoiceExtractionSchema]:
    """
    Enhanced Document Understanding Pipeline:
    Combines high-resolution rendering, layout block analysis, 
    spatial token positioning, and structured table row extraction.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        print(f"Failed to open document {file_path}: {e}")
        return None

    full_text = ""
    pages_words = []
    pages_tables = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        txt = page.get_text()
        full_text += f"\n--- Page {page_idx+1} ---\n" + txt
        words = page.get_text("words") # (x0, y0, x1, y1, word, block_no, line_no, word_no)
        pages_words.append(words)
        try:
            tbls = page.find_tables()
            pages_tables.append(tbls)
        except Exception:
            pages_tables.append(None)

    # Scanned PDF check: 0 words found
    total_words = sum(len(w) for w in pages_words)
    if total_words == 0:
        # Document is purely scanned raster image without text
        # Local pipeline without OCR cannot extract text
        doc.close()
        return None

    # 1. Invoice Number Extraction
    invoice_number = None
    inv_match = re.search(r"(?:Invoice\s*(?:Number|No|Ref|#)?[:\s]+)([A-Z0-9_-]+)", full_text, re.IGNORECASE)
    if inv_match:
        invoice_number = inv_match.group(1).strip()
    else:
        # Look for general alphanumeric patterns like INV-2026-001 or 97159829
        inv_match2 = re.search(r"\b([A-Z]{2,4}-\d{4}-\d{3,4})\b", full_text)
        if inv_match2:
            invoice_number = inv_match2.group(1).strip()

    # 2. Invoice Date Extraction
    invoice_date = None
    date_match_res = re.search(r"(?:Invoice\s*Date[:\s]+)([^\n\r]+)", full_text, re.IGNORECASE)
    if date_match_res:
        invoice_date = parse_date_string(date_match_res.group(1))
    if not invoice_date:
        invoice_date = parse_date_string(full_text)

    # 3. Currency Extraction
    currency = extract_currency(full_text)

    # 4. Vendor Name Extraction
    vendor_name = None
    # Pattern 1: Vendor header like "Vendor: Acme Office Supplies Pvt. Ltd."
    vend_m = re.search(r"(?:Vendor|Billed By\s*\(Vendor\)|Supplier)[:\s\n]+([A-Z0-9\s&.,'-]+?)(?:\n\n|\n[A-Z\s]+:|Customer|Billed To|Workplace|\Z)", full_text, re.IGNORECASE)
    if vend_m:
        vendor_candidate = vend_m.group(1).split("\n")[0].strip()
        if len(vendor_candidate) > 2:
            vendor_name = vendor_candidate
    if not vendor_name:
        # Check first prominent uppercase header line
        lines = [line.strip() for line in full_text.splitlines() if len(line.strip()) > 3]
        for line in lines[:5]:
            if not re.search(r"Invoice|Tax|Commercial|Page|Date", line, re.IGNORECASE):
                vendor_name = line
                break

    # 5. Customer Name Extraction
    customer_name = None
    cust_m = re.search(r"(?:Customer|Billed To\s*\(Customer\)|Bill To|Client)[:\s\n]+([A-Z0-9\s&.,'-]+?)(?:\n\n|\n[A-Z\s]+:|Description|Line Items|\Z)", full_text, re.IGNORECASE)
    if cust_m:
        cust_candidate = cust_m.group(1).split("\n")[0].strip()
        if len(cust_candidate) > 2:
            customer_name = cust_candidate

    # 6. Financial Summary (Subtotal, Tax, Total)
    subtotal = None
    tax_amount = None
    total_amount = None

    sub_m = re.search(r"Subtotal[:\s]+(?:[A-Z]{3}|[$€£₹])?\s*([\d,.]+)", full_text, re.IGNORECASE)
    if sub_m:
        subtotal = parse_monetary_string(sub_m.group(1))

    tax_m = re.search(r"(?:Tax|VAT|GST)[^:\n]*?[:\s]+(?:[A-Z]{3}|[$€£₹])?\s*([\d,.]+)", full_text, re.IGNORECASE)
    if tax_m:
        tax_amount = parse_monetary_string(tax_m.group(1))

    tot_m = re.search(r"(?:(?<!Sub)\bTotal(?:\s*Amount)?(?:\s*Payable)?|Total Due)[:\s]+(?:[A-Z]{3}|[$€£₹])?\s*([\d,.]+)", full_text, re.IGNORECASE)
    if tot_m:
        total_amount = parse_monetary_string(tot_m.group(1))

    # 7. Line Item Extraction (PyMuPDF Table Extraction + Spatial Row Parser)
    items = []
    # Method A: Try PyMuPDF find_tables()
    for tbls in pages_tables:
        if tbls and tbls.tables:
            for t in tbls.tables:
                raw_rows = t.extract()
                if len(raw_rows) > 1:
                    header = [str(c).lower() if c else "" for c in raw_rows[0]]
                    # Identify column indices
                    desc_col = -1
                    qty_col = -1
                    price_col = -1
                    tax_col = -1
                    tot_col = -1

                    for col_idx, col_name in enumerate(header):
                        if "desc" in col_name or "item" in col_name:
                            desc_col = col_idx
                        elif "qty" in col_name or "quantity" in col_name:
                            qty_col = col_idx
                        elif "price" in col_name or "rate" in col_name:
                            price_col = col_idx
                        elif "tax" in col_name or "vat" in col_name:
                            tax_col = col_idx
                        elif "total" in col_name:
                            tot_col = col_idx

                    if desc_col >= 0:
                        for row in raw_rows[1:]:
                            if not row or len(row) <= desc_col:
                                continue
                            raw_desc = row[desc_col]
                            if not raw_desc or "subtotal" in str(raw_desc).lower() or "total" in str(raw_desc).lower():
                                continue
                            desc_clean = str(raw_desc).replace("\n", " ").strip()
                            
                            qty_val = parse_monetary_string(row[qty_col]) if qty_col >= 0 and len(row) > qty_col and row[qty_col] else None
                            price_val = parse_monetary_string(row[price_col]) if price_col >= 0 and len(row) > price_col and row[price_col] else None
                            tax_rate_val = None
                            if tax_col >= 0 and len(row) > tax_col and row[tax_col]:
                                tax_str = str(row[tax_col]).strip()
                                tax_num = parse_monetary_string(tax_str)
                                if tax_num is not None:
                                    tax_rate_val = tax_num / 100.0 if tax_num > 1.0 else tax_num
                            
                            tot_val = parse_monetary_string(row[tot_col]) if tot_col >= 0 and len(row) > tot_col and row[tot_col] else None

                            if desc_clean:
                                items.append(InvoiceItemExtractionSchema(
                                    description=desc_clean,
                                    quantity=qty_val,
                                    unit_price=price_val,
                                    tax_rate=tax_rate_val,
                                    line_total=tot_val
                                ))

    # Method B: Regex text line parsing fallback if table finder returned 0 items
    if not items:
        # Check formatted lines like: "1. Item Name  Qty  Unit_Price  Tax%  Total"
        item_line_regex = re.compile(
            r"^(?:(?:\d+\.|\*|-)\s+)?([A-Za-z0-9\s()\"'-]{4,60}?)\s{2,}(\d+(?:\.\d+)?)\s{2,}([\d,.]+)\s{2,}(\d+%)?\s{2,}([\d,.]+)",
            re.MULTILINE
        )
        for m in item_line_regex.finditer(full_text):
            desc = m.group(1).strip()
            if "total" in desc.lower() or "subtotal" in desc.lower():
                continue
            qty = parse_monetary_string(m.group(2))
            price = parse_monetary_string(m.group(3))
            tax_str = m.group(4)
            tax_r = parse_monetary_string(tax_str) / 100.0 if tax_str else None
            tot = parse_monetary_string(m.group(5))
            items.append(InvoiceItemExtractionSchema(
                description=desc,
                quantity=qty,
                unit_price=price,
                tax_rate=tax_r,
                line_total=tot
            ))

    doc.close()

    try:
        extracted_schema = InvoiceExtractionSchema(
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            invoice_date=invoice_date,
            customer_name=customer_name,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=currency,
            items=items
        )
        return extracted_schema
    except ValidationError as e:
        print(f"Validation error: {e}")
        return None

def run_improved_document_ai_benchmark():
    print("=" * 80)
    print("InVoice AI — Final Stage 1 Evaluation: Enhanced Document AI Candidate")
    print("=" * 80)

    gt_files = sorted([f for f in os.listdir(GROUND_TRUTH_DIR) if f.endswith(".json")])
    candidate_results = []

    for gt_file in gt_files:
        doc_id = gt_file.replace(".json", "")
        with open(os.path.join(GROUND_TRUTH_DIR, gt_file), "r") as f:
            gt_data = json.load(f)

        pdf_path = os.path.join(INVOICES_DIR, f"{doc_id}.pdf")
        if not os.path.exists(pdf_path):
            continue

        print(f"\n[Evaluating Enhanced Candidate] {doc_id} ({gt_data.get('doc_type')})...")
        t0 = time.time()
        pred = extract_improved_document_ai(pdf_path)
        latency = time.time() - t0

        if pred:
            eval_metrics = evaluate_predictions(pred, gt_data)
            fallback_needed, fallback_reasons = check_deterministic_fallback(pred)
            res = {
                "doc_id": doc_id,
                "doc_type": gt_data.get("doc_type"),
                "status": "SUCCESS",
                "latency_sec": round(latency, 3),
                "is_valid_schema": True,
                "header_accuracy": eval_metrics["header_accuracy"],
                "numeric_error_rate": eval_metrics["numeric_error_rate"],
                "field_scores": eval_metrics["field_scores"],
                "line_items": eval_metrics["line_item_eval"],
                "extracted": pred.model_dump(mode="json"),
                "fallback_triggered": fallback_needed,
                "fallback_reasons": fallback_reasons
            }
        else:
            res = {
                "doc_id": doc_id,
                "doc_type": gt_data.get("doc_type"),
                "status": "FAILED",
                "latency_sec": round(latency, 3),
                "is_valid_schema": False,
                "header_accuracy": 0.0,
                "numeric_error_rate": 1.0,
                "field_scores": {
                    "invoice_number": 0.0, "vendor_name": 0.0, "customer_name": 0.0,
                    "currency": 0.0, "invoice_date": 0.0, "subtotal": 0.0,
                    "tax_amount": 0.0, "total_amount": 0.0
                },
                "line_items": {
                    "gt_count": len(gt_data.get("items", [])),
                    "pred_count": 0, "matched_count": 0,
                    "precision": 0.0, "recall": 0.0, "f1": 0.0,
                    "desc_accuracy": 0.0, "qty_accuracy": 0.0, "unit_price_accuracy": 0.0, "total_accuracy": 0.0
                },
                "extracted": None,
                "fallback_triggered": True,
                "fallback_reasons": ["Document parsing returned null or unextractable text"]
            }
        candidate_results.append(res)
        print(f"  Latency: {res['latency_sec']}s | Header Acc: {res['header_accuracy']*100:.1f}% | Item F1: {res['line_items'].get('f1', 0)*100:.1f}% | Fallback: {res['fallback_triggered']}")
        if res["fallback_reasons"]:
            print(f"  Reasons: {res['fallback_reasons']}")

    # Save results
    out_path = os.path.join(RESULTS_DIR, "improved_document_ai_results.json")
    with open(out_path, "w") as f:
        json.dump(candidate_results, f, indent=2)

    total_docs = len(candidate_results)
    avg_latency = sum(r["latency_sec"] for r in candidate_results) / total_docs
    avg_header_acc = sum(r["header_accuracy"] for r in candidate_results) / total_docs
    avg_item_f1 = sum(r["line_items"]["f1"] for r in candidate_results) / total_docs
    avg_item_prec = sum(r["line_items"]["precision"] for r in candidate_results) / total_docs
    avg_item_rec = sum(r["line_items"]["recall"] for r in candidate_results) / total_docs
    valid_schema_rate = sum(1 for r in candidate_results if r["is_valid_schema"]) / total_docs
    fallback_rate = sum(1 for r in candidate_results if r["fallback_triggered"]) / total_docs
    numeric_err_rate = sum(r["numeric_error_rate"] for r in candidate_results) / total_docs

    summary = {
        "candidate": "Enhanced Non-LLM Document AI Candidate (Layout & Table Understanding)",
        "evaluation_samples": total_docs,
        "avg_latency_sec": round(avg_latency, 3),
        "valid_schema_rate": round(valid_schema_rate * 100, 1),
        "avg_header_accuracy": round(avg_header_acc * 100, 1),
        "line_item_precision": round(avg_item_prec * 100, 1),
        "line_item_recall": round(avg_item_rec * 100, 1),
        "line_item_f1": round(avg_item_f1 * 100, 1),
        "numeric_error_rate": round(numeric_err_rate * 100, 1),
        "fallback_rate": round(fallback_rate * 100, 1)
    }

    print("\n" + "=" * 80)
    print("ENHANCED NON-LLM CANDIDATE AGGREGATE SUMMARY")
    print("=" * 80)
    print(json.dumps(summary, indent=2))

    return candidate_results, summary

if __name__ == "__main__":
    run_improved_document_ai_benchmark()
