from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional
import re
from app.services.ai_extractor import InvoiceExtractionSchema
from app.core.config import settings

ISO_4217_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY", "CHF", "CNY", "SGD",
    "AED", "SAR", "NZD", "SEK", "NOK", "DKK", "ZAR", "BRL", "MXN", "HKD",
    "KRW", "PLN", "TRY", "RUB", "IDR", "THB", "MYR", "PHP", "CZK", "ILS"
}

def to_decimal(val: Any) -> Optional[Decimal]:
    """Safely convert any numeric or string representation into a Decimal."""
    if val is None:
        return None
    try:
        # Convert through str to avoid binary floating-point representation artifacts
        val_str = str(val).strip()
        if not val_str:
            return None
        return Decimal(val_str)
    except (InvalidOperation, TypeError, ValueError):
        return None

def round_money(val: Optional[Decimal]) -> Optional[Decimal]:
    """Round a Decimal amount to 2 decimal places using standard ROUND_HALF_UP."""
    if val is None:
        return None
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def analyze_financials(extracted_data: InvoiceExtractionSchema) -> Dict[str, Any]:
    """
    Deterministic financial integrity analysis using exact Decimal monetary arithmetic.
    Validates arithmetic consistency, zero/negative quantities, missing fields,
    division-by-zero protection, and currency validity.
    """
    tolerance = Decimal(str(getattr(settings, "MONETARY_TOLERANCE", 0.05)))
    anomalies: List[str] = []

    # 1. Currency Validation
    currency_raw = extracted_data.currency
    currency_valid = False
    currency_error: Optional[str] = None
    currency_clean: Optional[str] = None

    if not currency_raw or not isinstance(currency_raw, str):
        currency_valid = False
        currency_error = "Currency code is missing or empty."
        anomalies.append(currency_error)
    else:
        norm_curr = currency_raw.strip().upper()
        if len(norm_curr) != 3 or not norm_curr.isalpha():
            currency_valid = False
            currency_error = f"Malformed currency code '{currency_raw}' (must be a 3-letter ISO code)."
            anomalies.append(currency_error)
        else:
            currency_clean = norm_curr
            currency_valid = True
            if currency_clean not in ISO_4217_CURRENCIES:
                # Non-standard 3-letter code
                currency_error = f"Currency code '{currency_clean}' is not recognized in standard ISO-4217 table."

    # 2. Extract and Validate Header Monetary Amounts
    subtotal_dec = to_decimal(extracted_data.subtotal)
    tax_dec = to_decimal(extracted_data.tax_amount)
    total_dec = to_decimal(extracted_data.total_amount)

    has_negative_amounts = False
    if subtotal_dec is not None and subtotal_dec < Decimal("0.00"):
        has_negative_amounts = True
        anomalies.append(f"Subtotal is negative: {subtotal_dec}")
    if tax_dec is not None and tax_dec < Decimal("0.00"):
        has_negative_amounts = True
        anomalies.append(f"Tax amount is negative: {tax_dec}")
    if total_dec is not None and total_dec < Decimal("0.00"):
        has_negative_amounts = True
        anomalies.append(f"Total amount is negative: {total_dec}")

    missing_total_amount = total_dec is None
    if missing_total_amount:
        anomalies.append("Total amount is missing from the invoice.")

    has_zero_total = total_dec == Decimal("0.00")

    # 3. Line Items Analysis & Consistency
    calculated_subtotal = Decimal("0.00")
    items_count = len(extracted_data.items)
    has_invalid_quantities = False
    has_invalid_unit_prices = False
    line_items_internal_consistent = True

    for idx, item in enumerate(extracted_data.items):
        item_desc = item.description or f"Item #{idx+1}"
        qty = to_decimal(item.quantity)
        price = to_decimal(item.unit_price)
        line_tot = to_decimal(item.line_total)

        # Check for invalid non-positive quantities
        if qty is not None:
            if qty < Decimal("0.00"):
                has_invalid_quantities = True
                anomalies.append(f"Negative quantity ({qty}) on item '{item_desc}'.")
            elif qty == Decimal("0.00"):
                has_invalid_quantities = True
                anomalies.append(f"Zero quantity on item '{item_desc}'.")

        # Check for invalid non-positive unit prices
        if price is not None:
            if price < Decimal("0.00"):
                has_invalid_unit_prices = True
                anomalies.append(f"Negative unit price ({price}) on item '{item_desc}'.")
            elif price == Decimal("0.00"):
                has_invalid_unit_prices = True
                anomalies.append(f"Zero unit price on item '{item_desc}'.")

        # Check internal line-item multiplication: qty * price == line_total
        if qty is not None and price is not None and line_tot is not None:
            expected_line_tot = round_money(qty * price)
            if abs(expected_line_tot - line_tot) > tolerance:
                line_items_internal_consistent = False
                anomalies.append(
                    f"Arithmetic mismatch on '{item_desc}': qty ({qty}) * unit price ({price}) = "
                    f"{expected_line_tot}, but line total is {line_tot}."
                )

        # Accumulate calculated subtotal
        if line_tot is not None:
            calculated_subtotal += line_tot
        elif qty is not None and price is not None:
            calculated_subtotal += round_money(qty * price)

    calculated_subtotal = round_money(calculated_subtotal)

    # If subtotal was not present in document header, use calculated_subtotal
    effective_subtotal = subtotal_dec if subtotal_dec is not None else calculated_subtotal
    effective_tax = tax_dec if tax_dec is not None else Decimal("0.00")

    # Check line items vs subtotal
    if items_count > 0 and subtotal_dec is not None:
        line_items_match_subtotal = abs(calculated_subtotal - subtotal_dec) <= tolerance
        if not line_items_match_subtotal:
            anomalies.append(
                f"Line items sum ({calculated_subtotal}) does not match invoice subtotal ({subtotal_dec}). "
                f"Discrepancy: {round_money(abs(calculated_subtotal - subtotal_dec))}."
            )
    else:
        line_items_match_subtotal = True

    # Check total consistency: subtotal + tax == total
    calculated_total = round_money(effective_subtotal + effective_tax)
    discount_detected: Optional[float] = None

    # Check for authoritatively established uniform tax rate
    established_tax_rate: Optional[Decimal] = None
    if subtotal_dec is not None and subtotal_dec > Decimal("0.00") and tax_dec is not None and tax_dec >= Decimal("0.00"):
        if tax_dec == Decimal("0.00"):
            established_tax_rate = Decimal("0.0000")
        else:
            candidate_ratio = tax_dec / subtotal_dec
            rounded_rate = candidate_ratio.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            expected_tax = round_money(subtotal_dec * rounded_rate)
            if abs(expected_tax - tax_dec) <= tolerance:
                established_tax_rate = rounded_rate

    if total_dec is not None:
        raw_diff = abs(total_dec - calculated_total)
        total_consistent = raw_diff <= tolerance

        if not total_consistent:
            # Check if total is lower than calculated_total (possible discount)
            if calculated_total > total_dec:
                implied_discount = round_money(calculated_total - total_dec)
                discount_detected = float(implied_discount)
                anomalies.append(
                    f"Invoice total ({total_dec}) is lower than calculated subtotal + tax ({calculated_total}); "
                    f"implied discount or deduction: {implied_discount}."
                )
            else:
                anomalies.append(
                    f"Total mismatch: invoice total ({total_dec}) does not equal subtotal ({effective_subtotal}) "
                    f"+ tax ({effective_tax}) = {calculated_total}. Discrepancy: {round_money(raw_diff)}."
                )
        diff_float = float(round_money(raw_diff))
    else:
        total_consistent = False
        diff_float = 0.0

    # Determine Overall Financial Status
    if missing_total_amount or has_negative_amounts:
        status = "INVALID_DATA"
    elif not total_consistent or not line_items_match_subtotal or not line_items_internal_consistent:
        status = "DISCREPANCY_DETECTED"
    else:
        status = "VALID"

    return {
        "status": status,
        "line_items_match_subtotal": line_items_match_subtotal,
        "line_items_internal_consistent": line_items_internal_consistent,
        "tax_consistent": total_consistent,
        "total_consistent": total_consistent,
        "subtotal": float(round_money(effective_subtotal)) if effective_subtotal is not None else 0.0,
        "calculated_subtotal": float(calculated_subtotal),
        "tax_amount": float(round_money(effective_tax)),
        "total_amount": float(round_money(total_dec)) if total_dec is not None else 0.0,
        "calculated_total": float(calculated_total),
        "difference": diff_float,
        "currency": currency_clean,
        "currency_valid": currency_valid,
        "currency_error": currency_error,
        "has_negative_amounts": has_negative_amounts,
        "has_invalid_quantities": has_invalid_quantities,
        "has_invalid_unit_prices": has_invalid_unit_prices,
        "has_zero_total": has_zero_total,
        "missing_total_amount": missing_total_amount,
        "discount_detected": discount_detected,
        "established_tax_rate": float(established_tax_rate) if established_tax_rate is not None else None,
        "anomalies": anomalies
    }
