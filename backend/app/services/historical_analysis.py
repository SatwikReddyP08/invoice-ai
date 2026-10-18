import re
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.invoice import Invoice, InvoiceItem, PipelineStatus
from app.services.ai_extractor import InvoiceExtractionSchema
from app.core.config import settings

def to_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        val_str = str(val).strip()
        if not val_str:
            return None
        return Decimal(val_str)
    except (InvalidOperation, TypeError, ValueError):
        return None

def normalize_vendor_name(text: Optional[str]) -> str:
    """
    Conservatively normalize vendor names by standardizing common corporate suffixes
    and punctuation, while strictly preserving core vendor identity.
    """
    if not text:
        return ""
    s = text.lower().strip()
    # Replace common separators and punctuation with spaces
    s = re.sub(r'[.,;:\(\)\[\]\-_/&]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()

    # Standardize known corporate suffixes
    suffixes = [
        "private limited", "pvt ltd", "pvt", "limited", "ltd",
        "incorporated", "inc", "corporation", "corp", "llc",
        "plc", "gmbh", "co", "company"
    ]
    for suf in suffixes:
        pattern = rf'\b{re.escape(suf)}\b'
        s = re.sub(pattern, '', s)

    return re.sub(r'\s+', ' ', s).strip()

def normalize_product_name(text: Optional[str]) -> str:
    """
    Conservatively normalize product descriptions.
    Extracts the core product title (first line before specifications/newlines)
    and removes incidental punctuation.
    """
    if not text:
        return ""
    # Take first line if description includes multi-line specifications
    first_line = text.split('\n')[0].strip()
    s = first_line.lower()
    # Strip common punctuation that might vary
    s = re.sub(r'[.,;:\(\)\[\]\-_/]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

# Alias for backward compatibility
normalize_text = normalize_vendor_name

def analyze_history(db: Session, extracted_data: InvoiceExtractionSchema, current_invoice_id: int) -> Dict[str, Any]:
    """
    Deterministic historical price comparison service.
    Implements:
    - Conservative vendor and product matching.
    - Same-vendor comparisons only.
    - Separation of unit price from quantity/tax/discounts.
    - Currency mismatch protection.
    - Duplicate invoice exclusion.
    - Current invoice exclusion.
    - Only eligible (SUCCESS) historical records.
    - Strict temporal ordering (invoice_date < current_date).
    - Documented same-date exclusion policy.
    - Historical outlier detection and sample size disclosure.
    - Explicit configurable price-change thresholds.
    """
    vendor_name = extracted_data.vendor_name
    if not vendor_name:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "message": "Current invoice has no vendor name available for historical comparison.",
            "is_duplicate_invoice": False,
            "historical_comparisons": [],
            "total_historical_invoices": 0
        }

    norm_current_vendor = normalize_vendor_name(vendor_name)
    if not norm_current_vendor:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "message": "Current invoice vendor name is blank after normalization.",
            "is_duplicate_invoice": False,
            "historical_comparisons": [],
            "total_historical_invoices": 0
        }

    current_date_raw = extracted_data.invoice_date
    if not current_date_raw:
        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "message": "Current invoice is missing an invoice date, preventing temporal comparison.",
            "is_duplicate_invoice": False,
            "historical_comparisons": [],
            "total_historical_invoices": 0
        }

    current_currency = (extracted_data.currency or "").strip().upper()
    current_date = current_date_raw.date() if isinstance(current_date_raw, datetime) else current_date_raw

    # 1. Fetch only eligible, successfully processed invoices from DB
    candidate_invoices = db.query(Invoice).filter(
        Invoice.id != current_invoice_id,
        Invoice.pipeline_status == PipelineStatus.SUCCESS
    ).all()

    historical_invoices: List[Invoice] = []
    duplicate_count = 0
    same_date_count = 0
    future_date_count = 0
    currency_mismatches_count = 0

    curr_inv_num = (extracted_data.invoice_number or "").strip()

    for inv in candidate_invoices:
        if not inv.vendor_name:
            continue

        # Same vendor check
        if normalize_vendor_name(inv.vendor_name) != norm_current_vendor:
            continue

        # Check for duplicate submission (same vendor and same invoice number)
        is_dup = bool(curr_inv_num and inv.invoice_number and inv.invoice_number.strip() == curr_inv_num)
        if is_dup:
            duplicate_count += 1
            # Exclude duplicate invoice from historical price baseline to avoid self-referential bias
            continue

        # Date checks
        if not inv.invoice_date:
            continue
        inv_d = inv.invoice_date.date() if isinstance(inv.invoice_date, datetime) else inv.invoice_date

        if inv_d > current_date:
            future_date_count += 1
            continue  # Strict ordering: future invoices excluded
        elif inv_d == current_date:
            same_date_count += 1
            # Documented same-date policy: excluded from price baseline to prevent temporal ambiguity
            continue

        # Currency check
        inv_curr = (inv.currency or "").strip().upper()
        if current_currency and inv_curr != current_currency:
            currency_mismatches_count += 1
            continue

        historical_invoices.append(inv)

    is_duplicate_invoice = duplicate_count > 0

    if not historical_invoices:
        if duplicate_count > 0:
            msg = (
                f"No prior baseline invoices available from {vendor_name}. "
                f"Previous submission(s) of invoice #{curr_inv_num} were detected and excluded from the price baseline "
                f"to prevent self-referential bias."
            )
        elif same_date_count > 0:
            msg = f"No strictly prior invoices available from {vendor_name}. {same_date_count} invoice(s) with identical dates were excluded per same-date policy."
        elif future_date_count > 0:
            msg = f"No eligible prior invoices available from {vendor_name} ({future_date_count} future-dated invoice(s) excluded)."
        elif currency_mismatches_count > 0:
            msg = f"No eligible prior invoices available from {vendor_name} in {current_currency} ({currency_mismatches_count} invoice(s) excluded due to currency mismatch)."
        else:
            msg = f"No historical invoices available from {vendor_name} with matching currency."

        return {
            "status": "INSUFFICIENT_EVIDENCE",
            "message": msg,
            "is_duplicate_invoice": is_duplicate_invoice,
            "duplicate_invoices_excluded": duplicate_count,
            "same_date_invoices_excluded": same_date_count,
            "future_invoices_excluded": future_date_count,
            "currency_mismatches_excluded": currency_mismatches_count,
            "historical_comparisons": [],
            "total_historical_invoices": 0
        }

    # Sort historical invoices by invoice_date ascending
    historical_invoices.sort(key=lambda x: x.invoice_date)

    # 2. Build map of historical product prices
    hist_items_map: Dict[str, List[Dict[str, Any]]] = {}
    for inv in historical_invoices:
        for item in inv.items:
            norm_prod = normalize_product_name(item.description)
            price_dec = to_decimal(item.unit_price)
            if not norm_prod or price_dec is None or price_dec <= Decimal("0.00"):
                continue

            if norm_prod not in hist_items_map:
                hist_items_map[norm_prod] = []
            hist_items_map[norm_prod].append({
                "unit_price": price_dec,
                "invoice_date": inv.invoice_date,
                "invoice_number": inv.invoice_number
            })

    # Read configurable thresholds
    significant_threshold = Decimal(str(getattr(settings, "PRICE_CHANGE_THRESHOLD_PERCENT", 10.0)))
    material_threshold = Decimal(str(getattr(settings, "PRICE_CHANGE_MATERIAL_PERCENT", 25.0)))

    comparisons = []

    for current_item in extracted_data.items:
        product_desc = current_item.description or "Unknown Product"
        norm_prod = normalize_product_name(product_desc)
        curr_price_dec = to_decimal(current_item.unit_price)

        if curr_price_dec is None:
            comparisons.append({
                "product": product_desc,
                "status": "INSUFFICIENT_EVIDENCE",
                "message": "Missing unit price on current item."
            })
            continue

        if curr_price_dec <= Decimal("0.00"):
            comparisons.append({
                "product": product_desc,
                "status": "INSUFFICIENT_EVIDENCE",
                "message": f"Non-positive unit price ({curr_price_dec}) on current item."
            })
            continue

        hist_records = hist_items_map.get(norm_prod, [])
        if not hist_records:
            comparisons.append({
                "product": product_desc,
                "status": "INSUFFICIENT_EVIDENCE",
                "message": "No reliable historical price available for this product from this vendor."
            })
            continue

        prices = [r["unit_price"] for r in hist_records]
        sample_size = len(prices)

        min_price = min(prices)
        max_price = max(prices)
        avg_price = (sum(prices) / Decimal(str(sample_size))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        sorted_prices = sorted(prices)
        mid = sample_size // 2
        if sample_size % 2 == 1:
            median_price = sorted_prices[mid]
        else:
            median_price = ((sorted_prices[mid - 1] + sorted_prices[mid]) / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Outlier detection (for sample_size >= 3)
        outliers: List[Decimal] = []
        if sample_size >= 3 and median_price > Decimal("0.00"):
            outliers = [p for p in prices if (p > median_price * Decimal("2.5") or p < median_price * Decimal("0.4"))]

        latest_record = max(hist_records, key=lambda x: x["invoice_date"])
        latest_price = latest_record["unit_price"]

        # Safe division for percentage changes
        abs_change_avg = curr_price_dec - avg_price
        abs_change_latest = curr_price_dec - latest_price

        pct_change_avg = ((curr_price_dec - avg_price) / avg_price * Decimal("100.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pct_change_latest = ((curr_price_dec - latest_price) / latest_price * Decimal("100.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Categorize change
        if abs(pct_change_latest) < Decimal("1.00"):
            change_category = "UNCHANGED"
        elif pct_change_latest >= material_threshold:
            change_category = "MATERIAL_INCREASE"
        elif pct_change_latest >= significant_threshold:
            change_category = "SIGNIFICANT_INCREASE"
        elif pct_change_latest > Decimal("0.00"):
            change_category = "MINOR_INCREASE"
        elif pct_change_latest <= -material_threshold:
            change_category = "MATERIAL_DECREASE"
        elif pct_change_latest <= -significant_threshold:
            change_category = "SIGNIFICANT_DECREASE"
        else:
            change_category = "MINOR_DECREASE"

        threshold_exceeded = (
            abs(pct_change_latest) >= significant_threshold or
            abs(pct_change_avg) >= significant_threshold
        )
        is_actionable_increase = (
            pct_change_latest >= significant_threshold or
            pct_change_avg >= significant_threshold
        )
        is_price_increase = (
            pct_change_latest > Decimal("0.00") or
            pct_change_avg > Decimal("0.00")
        )
        is_price_decrease = (
            pct_change_latest < Decimal("0.00") or
            pct_change_avg < Decimal("0.00")
        )

        comparisons.append({
            "product": product_desc,
            "status": "COMPARISON_AVAILABLE",
            "current_unit_price": round(float(curr_price_dec), 2),
            "latest_previous_unit_price": round(float(latest_price), 2),
            "historical_average_unit_price": round(float(avg_price), 2),
            "historical_median_unit_price": round(float(median_price), 2),
            "historical_min_unit_price": round(float(min_price), 2),
            "historical_max_unit_price": round(float(max_price), 2),
            "absolute_change": round(float(abs_change_avg), 2),
            "absolute_change_from_previous": round(float(abs_change_latest), 2),
            "percentage_change_from_average": round(float(pct_change_avg), 2),
            "percentage_change_from_previous": round(float(pct_change_latest), 2),
            "change_category": change_category,
            "threshold_exceeded": threshold_exceeded,
            "is_actionable_increase": is_actionable_increase,
            "is_price_increase": is_price_increase,
            "is_price_decrease": is_price_decrease,
            "sample_size": sample_size,
            "low_sample_size": sample_size < 2,
            "outliers_detected": [round(float(o), 2) for o in outliers],
            "comparable_invoice_count": sample_size
        })

    return {
        "status": "ANALYZED",
        "historical_comparisons": comparisons,
        "is_duplicate_invoice": is_duplicate_invoice,
        "duplicate_invoices_excluded": duplicate_count,
        "same_date_invoices_excluded": same_date_count,
        "future_invoices_excluded": future_date_count,
        "currency_mismatches_excluded": currency_mismatches_count,
        "total_historical_invoices": len(historical_invoices),
        "significant_threshold_percent": float(significant_threshold),
        "material_threshold_percent": float(material_threshold)
    }
