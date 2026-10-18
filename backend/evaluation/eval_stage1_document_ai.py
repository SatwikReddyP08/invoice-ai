import os
import sys
import json
import time
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, ValidationError

# Add backend to sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.config import settings
from app.services.ai_extractor import (
    InvoiceExtractionSchema,
    InvoiceItemExtractionSchema,
    extract_invoice as baseline_extract_invoice
)

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
INVOICES_DIR = os.path.join(DATASET_DIR, "invoices")
GROUND_TRUTH_DIR = os.path.join(DATASET_DIR, "ground_truth")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def normalize_str(s: Optional[str]) -> str:
    if not s:
        return ""
    # Remove punctuation and extra whitespace, lowercase
    clean = re.sub(r"[^\w\s]", " ", str(s).lower())
    return " ".join(clean.split())

def string_similarity(a: Optional[str], b: Optional[str]) -> float:
    na, nb = normalize_str(a), normalize_str(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Check substring inclusion
    if na in nb or nb in na:
        return 0.85
    # Token jaccard
    sa, sb = set(na.split()), set(nb.split())
    intersection = len(sa.intersection(sb))
    union = len(sa.union(sb))
    return intersection / union if union > 0 else 0.0

def float_match(a: Optional[float], b: Optional[float], tol: float = 0.05) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
        if abs(fa - fb) <= tol:
            return True
        if fb != 0 and abs(fa - fb) / abs(fb) <= 0.01:
            return True
        return False
    except Exception:
        return False

def date_match(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    sa = str(a).strip()
    sb = str(b).strip()
    return sa == sb

def evaluate_line_items(pred_items: List[Any], gt_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not gt_items and not pred_items:
        return {
            "gt_count": 0,
            "pred_count": 0,
            "matched_count": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "desc_accuracy": 1.0,
            "qty_accuracy": 1.0,
            "unit_price_accuracy": 1.0,
            "total_accuracy": 1.0
        }
    if not gt_items:
        return {
            "gt_count": 0,
            "pred_count": len(pred_items),
            "matched_count": 0,
            "precision": 0.0,
            "recall": 1.0,
            "f1": 0.0,
            "desc_accuracy": 0.0,
            "qty_accuracy": 0.0,
            "unit_price_accuracy": 0.0,
            "total_accuracy": 0.0
        }
    if not pred_items:
        return {
            "gt_count": len(gt_items),
            "pred_count": 0,
            "matched_count": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "desc_accuracy": 0.0,
            "qty_accuracy": 0.0,
            "unit_price_accuracy": 0.0,
            "total_accuracy": 0.0
        }

    # Match each gt item with best pred item
    matched_gt = set()
    matched_pred = set()
    item_metrics = []

    for g_idx, gt in enumerate(gt_items):
        best_p_idx = -1
        best_sim = 0.0
        for p_idx, pred in enumerate(pred_items):
            if p_idx in matched_pred:
                continue
            p_dict = pred if isinstance(pred, dict) else pred.model_dump()
            sim = string_similarity(gt.get("description"), p_dict.get("description"))
            if sim > best_sim:
                best_sim = sim
                best_p_idx = p_idx
        
        if best_p_idx >= 0 and best_sim >= 0.4:
            matched_gt.add(g_idx)
            matched_pred.add(best_p_idx)
            pred_obj = pred_items[best_p_idx]
            p_dict = pred_obj if isinstance(pred_obj, dict) else pred_obj.model_dump()

            item_metrics.append({
                "desc_match": best_sim >= 0.7,
                "qty_match": float_match(gt.get("quantity"), p_dict.get("quantity")),
                "price_match": float_match(gt.get("unit_price"), p_dict.get("unit_price")),
                "total_match": float_match(gt.get("line_total"), p_dict.get("line_total"))
            })

    matched_count = len(matched_gt)
    precision = matched_count / len(pred_items) if pred_items else 0.0
    recall = matched_count / len(gt_items) if gt_items else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    desc_acc = sum(1 for m in item_metrics if m["desc_match"]) / matched_count if matched_count > 0 else 0.0
    qty_acc = sum(1 for m in item_metrics if m["qty_match"]) / matched_count if matched_count > 0 else 0.0
    price_acc = sum(1 for m in item_metrics if m["price_match"]) / matched_count if matched_count > 0 else 0.0
    tot_acc = sum(1 for m in item_metrics if m["total_match"]) / matched_count if matched_count > 0 else 0.0

    return {
        "gt_count": len(gt_items),
        "pred_count": len(pred_items),
        "matched_count": matched_count,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "desc_accuracy": round(desc_acc, 4),
        "qty_accuracy": round(qty_acc, 4),
        "unit_price_accuracy": round(price_acc, 4),
        "total_accuracy": round(tot_acc, 4)
    }

def check_deterministic_fallback(extracted: Optional[InvoiceExtractionSchema]) -> Tuple[bool, List[str]]:
    """
    Evaluates explicit testable fallback criteria defined in Section 7.
    Returns (should_fallback, reasons).
    """
    reasons = []
    if extracted is None:
        return True, ["Model inference failed or returned None"]

    # 1. Critical Header completeness
    if not extracted.invoice_number:
        reasons.append("Missing required invoice_number")
    if not extracted.vendor_name:
        reasons.append("Missing required vendor_name")
    if extracted.total_amount is None:
        reasons.append("Missing required total_amount")

    # 2. Mathematical Consistency check
    # Check subtotal + tax == total (if both subtotal and tax present)
    if extracted.subtotal is not None and extracted.tax_amount is not None and extracted.total_amount is not None:
        calc_tot = extracted.subtotal + extracted.tax_amount
        if not float_match(calc_tot, extracted.total_amount, tol=0.5):
            reasons.append(f"Header math inconsistency: subtotal ({extracted.subtotal}) + tax ({extracted.tax_amount}) != total ({extracted.total_amount})")

    # Check sum of line items vs subtotal / total
    if extracted.items:
        items_total = 0.0
        valid_items_math = True
        for it in extracted.items:
            if it.line_total is not None:
                items_total += it.line_total
            elif it.quantity is not None and it.unit_price is not None:
                items_total += it.quantity * it.unit_price
            else:
                valid_items_math = False
        
        if valid_items_math and extracted.subtotal is not None:
            if not float_match(items_total, extracted.subtotal, tol=1.0):
                reasons.append(f"Line items sum ({items_total:.2f}) does not match subtotal ({extracted.subtotal:.2f})")

    should_fallback = len(reasons) > 0
    return should_fallback, reasons

def evaluate_predictions(pred: InvoiceExtractionSchema, gt: Dict[str, Any]) -> Dict[str, Any]:
    pred_dict = pred.model_dump()
    
    inv_num_match = string_similarity(pred_dict.get("invoice_number"), gt.get("invoice_number")) >= 0.8
    vendor_match = string_similarity(pred_dict.get("vendor_name"), gt.get("vendor_name")) >= 0.7
    cust_match = string_similarity(pred_dict.get("customer_name"), gt.get("customer_name")) >= 0.7
    curr_match = normalize_str(pred_dict.get("currency")) == normalize_str(gt.get("currency"))
    date_m = date_match(pred_dict.get("invoice_date"), gt.get("invoice_date"))
    
    subtotal_m = float_match(pred_dict.get("subtotal"), gt.get("subtotal"))
    tax_m = float_match(pred_dict.get("tax_amount"), gt.get("tax_amount"))
    total_m = float_match(pred_dict.get("total_amount"), gt.get("total_amount"))

    line_item_eval = evaluate_line_items(pred_dict.get("items", []), gt.get("items", []))

    field_scores = {
        "invoice_number": 1.0 if inv_num_match else 0.0,
        "vendor_name": 1.0 if vendor_match else 0.0,
        "customer_name": 1.0 if cust_match else 0.0,
        "currency": 1.0 if curr_match else 0.0,
        "invoice_date": 1.0 if date_m else 0.0,
        "subtotal": 1.0 if subtotal_m else 0.0,
        "tax_amount": 1.0 if tax_m else 0.0,
        "total_amount": 1.0 if total_m else 0.0,
    }

    numeric_errors = 0
    numeric_checks = 0
    for field in ["subtotal", "tax_amount", "total_amount"]:
        if gt.get(field) is not None:
            numeric_checks += 1
            if not float_match(pred_dict.get(field), gt.get(field)):
                numeric_errors += 1

    header_accuracy = sum(field_scores.values()) / len(field_scores)

    return {
        "field_scores": field_scores,
        "header_accuracy": round(header_accuracy, 4),
        "numeric_error_rate": round(numeric_errors / numeric_checks, 4) if numeric_checks > 0 else 0.0,
        "line_item_eval": line_item_eval
    }

def run_evaluation_suite():
    print("=" * 80)
    print("InVoice AI — Stage 1 Document Understanding Evaluation Suite")
    print("=" * 80)

    # Load dataset
    gt_files = [f for f in os.listdir(GROUND_TRUTH_DIR) if f.endswith(".json")]
    gt_files.sort()
    
    print(f"Loaded {len(gt_files)} ground truth documents for evaluation.")

    baseline_results = []
    
    for gt_file in gt_files:
        doc_id = gt_file.replace(".json", "")
        with open(os.path.join(GROUND_TRUTH_DIR, gt_file), "r") as f:
            gt_data = json.load(f)
            
        pdf_path = os.path.join(INVOICES_DIR, f"{doc_id}.pdf")
        if not os.path.exists(pdf_path):
            print(f"Warning: PDF file {pdf_path} not found, skipping.")
            continue
            
        print(f"\n[Evaluating Baseline] {doc_id} ({gt_data.get('doc_type')})...")
        t0 = time.time()
        try:
            pred_schema = baseline_extract_invoice(pdf_path)
            latency = time.time() - t0
            is_valid_schema = True
        except Exception as e:
            latency = time.time() - t0
            print(f"Baseline extraction failed for {doc_id}: {e}")
            pred_schema = None
            is_valid_schema = False

        if pred_schema:
            eval_metrics = evaluate_predictions(pred_schema, gt_data)
            fallback_needed, fallback_reasons = check_deterministic_fallback(pred_schema)
            res = {
                "doc_id": doc_id,
                "doc_type": gt_data.get("doc_type"),
                "status": "SUCCESS",
                "latency_sec": round(latency, 2),
                "is_valid_schema": is_valid_schema,
                "header_accuracy": eval_metrics["header_accuracy"],
                "numeric_error_rate": eval_metrics["numeric_error_rate"],
                "field_scores": eval_metrics["field_scores"],
                "line_items": eval_metrics["line_item_eval"],
                "extracted": pred_schema.model_dump(mode="json"),
                "fallback_triggered": fallback_needed,
                "fallback_reasons": fallback_reasons
            }
        else:
            res = {
                "doc_id": doc_id,
                "doc_type": gt_data.get("doc_type"),
                "status": "FAILED",
                "latency_sec": round(latency, 2),
                "is_valid_schema": False,
                "header_accuracy": 0.0,
                "numeric_error_rate": 1.0,
                "field_scores": {},
                "line_items": {"f1": 0.0, "precision": 0.0, "recall": 0.0},
                "extracted": None,
                "fallback_triggered": True,
                "fallback_reasons": ["Extraction returned null or exception"]
            }
        baseline_results.append(res)
        print(f"  Latency: {res['latency_sec']}s | Header Acc: {res['header_accuracy']*100:.1f}% | Item F1: {res['line_items'].get('f1', 0)*100:.1f}% | Fallback: {res['fallback_triggered']}")

    # Save baseline results
    baseline_out = os.path.join(RESULTS_DIR, "baseline_groq_qwen_results.json")
    with open(baseline_out, "w") as f:
        json.dump(baseline_results, f, indent=2)
    print(f"\nBaseline results saved to {baseline_out}")

    # Compute Aggregate Baseline Summary
    total_docs = len(baseline_results)
    avg_latency = sum(r["latency_sec"] for r in baseline_results) / total_docs
    avg_header_acc = sum(r["header_accuracy"] for r in baseline_results) / total_docs
    avg_item_f1 = sum(r["line_items"]["f1"] for r in baseline_results) / total_docs
    avg_item_prec = sum(r["line_items"]["precision"] for r in baseline_results) / total_docs
    avg_item_rec = sum(r["line_items"]["recall"] for r in baseline_results) / total_docs
    valid_schema_rate = sum(1 for r in baseline_results if r["is_valid_schema"]) / total_docs
    fallback_rate = sum(1 for r in baseline_results if r["fallback_triggered"]) / total_docs

    summary = {
        "candidate": "Baseline: Groq / Qwen Vision (qwen/qwen3.8-27b)",
        "evaluation_samples": total_docs,
        "avg_latency_sec": round(avg_latency, 2),
        "valid_schema_rate": round(valid_schema_rate, 4),
        "avg_header_accuracy": round(avg_header_acc, 4),
        "line_item_precision": round(avg_item_prec, 4),
        "line_item_recall": round(avg_item_rec, 4),
        "line_item_f1": round(avg_item_f1, 4),
        "fallback_rate": round(fallback_rate, 4)
    }

    summary_out = os.path.join(RESULTS_DIR, "baseline_summary.json")
    with open(summary_out, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("BASELINE AGGREGATE PERFORMANCE SUMMARY")
    print("=" * 80)
    print(json.dumps(summary, indent=2))

    return baseline_results, summary

if __name__ == "__main__":
    run_evaluation_suite()
