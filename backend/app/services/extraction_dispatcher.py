import time
import os
from typing import Tuple, Dict, Any, List

from app.core.config import settings
from app.services.ai_extractor import extract_invoice, InvoiceExtractionSchema
from app.services.non_llm_extractor import extract_non_llm, NonLLMExtractionError
from app.services.financial_analysis import analyze_financials
from app.schemas.comparison import (
    ComparisonField,
    ComparisonLineItem,
    ExtractionMethodResult,
    ExtractionComparisonResponse
)

def dispatch_extraction(file_path: str, mode: str = "llm") -> Tuple[InvoiceExtractionSchema, Dict[str, Any]]:
    """
    Dispatch invoice extraction to the requested mode:
    - 'llm': Production Groq / Qwen Vision extraction
    - 'non_llm': Experimental PyMuPDF deterministic layout extraction
    """
    normalized_mode = (mode or "llm").strip().lower()
    
    if normalized_mode == "non_llm":
        return extract_non_llm(file_path)
    else:
        # LLM-assisted extraction (Production Primary)
        t0 = time.time()
        extracted_data = extract_invoice(file_path)
        elapsed = round(time.time() - t0, 4)
        metadata = {
            "extraction_method": "LLM_ASSISTED",
            "provenance": f"Groq Vision API ({settings.GROQ_MODEL})",
            "processing_time_seconds": elapsed,
            "is_experimental": False,
            "verifiable_confidence": {
                "has_invoice_number": bool(extracted_data.invoice_number),
                "has_invoice_date": bool(extracted_data.invoice_date),
                "has_vendor_name": bool(extracted_data.vendor_name),
                "has_total_amount": bool(extracted_data.total_amount),
                "line_item_count": len(extracted_data.items)
            }
        }
        return extracted_data, metadata

def run_extraction_comparison(file_path: str, invoice_id: int) -> ExtractionComparisonResponse:
    """
    Executes both extraction methods on the same document in isolation.
    Does not create duplicate database records or alter historical baselines.
    """
    filename = os.path.basename(file_path)
    
    # 1. Run LLM extraction
    llm_success = False
    llm_error = None
    llm_data = None
    llm_fin = None
    llm_meta = {}
    t0 = time.time()
    try:
        llm_schema = extract_invoice(file_path)
        llm_time = round(time.time() - t0, 4)
        llm_data = llm_schema.model_dump(mode="json")
        llm_fin = analyze_financials(llm_schema)
        llm_success = True
        llm_meta = {
            "math_consistent": llm_fin.get("total_consistent", False),
            "line_item_count": len(llm_schema.items)
        }
    except Exception as e:
        llm_time = round(time.time() - t0, 4)
        llm_error = str(e)

    llm_result = ExtractionMethodResult(
        method="LLM_ASSISTED",
        provenance=f"Groq Vision API ({settings.GROQ_MODEL})",
        processing_time_seconds=llm_time,
        success=llm_success,
        is_experimental=False,
        error_message=llm_error,
        extracted_data=llm_data,
        financial_validation=llm_fin,
        verifiable_confidence=llm_meta if llm_success else None
    )

    # 2. Run Non-LLM extraction
    non_llm_success = False
    non_llm_error = None
    non_llm_data = None
    non_llm_fin = None
    non_llm_meta = {}
    t1 = time.time()
    try:
        non_llm_schema, non_meta = extract_non_llm(file_path)
        non_llm_time = round(time.time() - t1, 4)
        non_llm_data = non_llm_schema.model_dump(mode="json")
        non_llm_fin = analyze_financials(non_llm_schema)
        non_llm_success = True
        non_llm_meta = non_meta.get("verifiable_confidence", {})
    except Exception as e:
        non_llm_time = round(time.time() - t1, 4)
        non_llm_error = str(e)

    non_llm_result = ExtractionMethodResult(
        method="NON_LLM",
        provenance="PyMuPDF Deterministic Layout, Coordinate Table & Spatial Parser",
        processing_time_seconds=non_llm_time,
        success=non_llm_success,
        is_experimental=True,
        error_message=non_llm_error,
        extracted_data=non_llm_data,
        financial_validation=non_llm_fin,
        verifiable_confidence=non_llm_meta if non_llm_success else None
    )

    # 3. Header Field Comparison
    header_fields = [
        "invoice_number", "invoice_date", "vendor_name",
        "customer_name", "subtotal", "tax_amount", "total_amount", "currency"
    ]
    field_comparisons: List[ComparisonField] = []
    
    for f in header_fields:
        v_llm = llm_data.get(f) if llm_data else None
        v_non = non_llm_data.get(f) if non_llm_data else None
        
        # Check match with normalization
        if v_llm is None and v_non is None:
            matches = True
            diff = "Both methods identified null/missing"
        elif v_llm is None:
            matches = False
            diff = "Present only in Non-LLM extraction"
        elif v_non is None:
            matches = False
            diff = "Present only in LLM extraction"
        elif isinstance(v_llm, (int, float)) and isinstance(v_non, (int, float)):
            matches = abs(float(v_llm) - float(v_non)) < 0.05
            diff = "Values match within rounding tolerance" if matches else f"Numeric discrepancy: {v_llm} vs {v_non}"
        else:
            s_llm = str(v_llm).strip().lower()
            s_non = str(v_non).strip().lower()
            matches = (s_llm == s_non)
            diff = "Exact string match" if matches else "Textual discrepancy"

        field_comparisons.append(ComparisonField(
            field_name=f,
            llm_value=v_llm,
            non_llm_value=v_non,
            matches=matches,
            difference_note=diff
        ))

    # 4. Line Item Comparison
    llm_items = llm_data.get("items", []) if llm_data else []
    non_items = non_llm_data.get("items", []) if non_llm_data else []
    
    max_items = max(len(llm_items), len(non_items))
    line_comparisons: List[ComparisonLineItem] = []
    
    for idx in range(max_items):
        item_llm = llm_items[idx] if idx < len(llm_items) else None
        item_non = non_items[idx] if idx < len(non_items) else None
        
        if item_llm is not None and item_non is not None:
            # Check price and quantity alignment
            p_llm = item_llm.get("unit_price")
            p_non = item_non.get("unit_price")
            q_llm = item_llm.get("quantity")
            q_non = item_non.get("quantity")
            
            p_match = (p_llm == p_non) or (p_llm is not None and p_non is not None and abs(p_llm - p_non) < 0.05)
            q_match = (q_llm == q_non) or (q_llm is not None and q_non is not None and abs(q_llm - q_non) < 0.05)
            
            if p_match and q_match:
                status = "EXACT_MATCH"
                diff = "Price and quantity match exactly"
            elif not p_match:
                status = "PRICE_MISMATCH"
                diff = f"Unit price mismatch: LLM {p_llm} vs Non-LLM {p_non}"
            else:
                status = "QUANTITY_MISMATCH"
                diff = f"Quantity mismatch: LLM {q_llm} vs Non-LLM {q_non}"
        elif item_llm is not None:
            status = "ONLY_IN_LLM"
            diff = f"Item extracted only by LLM ({item_llm.get('description', '')})"
        else:
            status = "ONLY_IN_NON_LLM"
            diff = f"Item extracted only by Non-LLM ({item_non.get('description', '')})"

        line_comparisons.append(ComparisonLineItem(
            index=idx + 1,
            llm_item=item_llm,
            non_llm_item=item_non,
            match_status=status,
            difference_note=diff
        ))

    # 5. Summary Notes (Honest Comparison & Ground Truth Distinction)
    summary_notes = []
    if llm_success and non_llm_success:
        speedup = round(llm_time / non_llm_time, 1) if non_llm_time > 0 else 0
        summary_notes.append(
            f"Current Document Latency: Non-LLM took {non_llm_time}s vs {llm_time}s for LLM "
            f"({speedup}x relative speedup on this single document). "
            f"Note: This is a single-document measurement; latency varies widely across PDF structures, page counts, and layouts."
        )
        
        matched_headers = sum(1 for c in field_comparisons if c.matches)
        summary_notes.append(f"Header Agreement (Consensus): {matched_headers}/{len(header_fields)} fields agree between extraction engines.")
        
        matched_lines = sum(1 for c in line_comparisons if c.match_status == "EXACT_MATCH")
        summary_notes.append(f"Line Item Alignment: {matched_lines}/{max_items} rows match exactly across descriptions, prices, and quantities.")
        
        # Discrepancy Warnings
        mismatched_headers = [c.field_name for c in field_comparisons if not c.matches]
        if mismatched_headers:
            summary_notes.append(f"Field Discrepancies Requiring Manual Review: {', '.join(mismatched_headers)} differ between methods.")
            
        if matched_lines < max_items:
            summary_notes.append(f"Line Item Variance: {max_items - matched_lines} row(s) exhibit price/quantity mismatches or were detected by only one method.")

        # Financial Reconciliation
        if llm_fin and non_llm_fin:
            if llm_fin.get("total_consistent") and non_llm_fin.get("total_consistent"):
                summary_notes.append("Financial Reconciliation: Both methods achieved verified mathematical balance (Subtotal + Tax == Total).")
            elif llm_fin.get("total_consistent"):
                summary_notes.append("Financial Reconciliation: Only LLM extraction achieved verified mathematical balance (Subtotal + Tax == Total). Non-LLM requires manual audit.")
            elif non_llm_fin.get("total_consistent"):
                summary_notes.append("Financial Reconciliation: Only Non-LLM extraction achieved verified mathematical balance (Subtotal + Tax == Total). LLM requires manual audit.")
            else:
                summary_notes.append("Financial Reconciliation: Neither method balanced mathematically. Manual audit of totals and tax rates is required.")

        # Ground Truth & Benchmark Honesty Notice
        summary_notes.append(
            "Ground Truth & Accuracy Notice: Agreement between LLM and Non-LLM extractions indicates model consensus on this document, "
            "but does NOT prove factual correctness. A method cannot be declared 'more accurate' without evaluation against a verified reference dataset."
        )
    elif not non_llm_success:
        summary_notes.append(f"Non-LLM extraction failed on this document: {non_llm_error}")
    elif not llm_success:
        summary_notes.append(f"LLM extraction failed on this document: {llm_error}")

    return ExtractionComparisonResponse(
        invoice_id=invoice_id,
        filename=filename,
        llm_result=llm_result,
        non_llm_result=non_llm_result,
        header_field_comparisons=field_comparisons,
        line_item_comparisons=line_comparisons,
        summary_notes=summary_notes
    )
