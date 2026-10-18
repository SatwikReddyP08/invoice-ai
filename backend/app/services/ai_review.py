from pydantic import BaseModel, Field
import groq
from app.core.config import settings
import json
import re
from typing import Dict, Any, List, Optional
import logging

class FindingSchema(BaseModel):
    type: str = Field(description="One of: 'PRICE_CHANGE', 'QUANTITY_VARIATION', 'FINANCIAL_DISCREPANCY', 'CURRENCY_MISMATCH', 'DUPLICATE_INVOICE', 'NO_ANOMALY', 'INSUFFICIENT_EVIDENCE'")
    severity: str = Field(description="One of: 'NONE', 'LOW', 'MEDIUM', 'HIGH'")
    product: Optional[str] = Field(description="The product name, or null if not applicable")
    evidence: str = Field(description="Exact evidence from the deterministic input, e.g. 'Current unit price is 31.1% above historical average'")
    explanation: str = Field(description="Objective, non-accusatory explanation of what the evidence indicates.")
    
    model_config = {"extra": "forbid"}

class InvoiceReviewSchema(BaseModel):
    status: str = Field(description="One of: 'NORMAL', 'REVIEW_RECOMMENDED', 'INSUFFICIENT_EVIDENCE'")
    review_recommendation: str = Field(description="One of: 'NO_ACTION_REQUIRED', 'REVIEW_RECOMMENDED', 'INSUFFICIENT_DATA'")
    findings: List[FindingSchema] = Field(description="List of key findings strictly reflecting deterministic evidence")
    explanation: str = Field(description="Explanation of the overall review decision based ONLY on the evidence provided.")
    
    model_config = {"extra": "forbid"}

BANNED_ACCUSATORY_WORDS = re.compile(
    r"\b(fraud|fraudulent|scam|theft|embezzlement|criminal|malicious|illegal)\b",
    re.IGNORECASE
)

def sanitize_text(text: str) -> str:
    """Neutralize accusatory terminology, maintaining objective procurement standards."""
    return BANNED_ACCUSATORY_WORDS.sub("price variance requiring verification", text)

def post_validate_review(review: InvoiceReviewSchema, evidence: Dict[str, Any]) -> InvoiceReviewSchema:
    """
    Deterministic post-validation layer:
    - Enforces evidence fidelity.
    - Prevents hallucinated products, prices, or unsupported claims.
    - Ensures insufficient evidence is explicitly respected.
    - Guarantees price changes are not labeled fraudulent.
    """
    hist_ctx = evidence.get("historical_context", {})
    fin_val = evidence.get("financial_validation", {})
    
    hist_status = hist_ctx.get("status")
    hist_comparisons = hist_ctx.get("historical_comparisons", [])
    valid_products = {
        c.get("product").strip().lower(): c 
        for c in hist_comparisons if c.get("product") and c.get("status") == "COMPARISON_AVAILABLE"
    }
    
    is_genuine_dup = bool(hist_ctx.get("is_duplicate_invoice"))
    dup_count = hist_ctx.get("duplicate_invoices_excluded", 1)
    inv_num = evidence.get("invoice", {}).get("invoice_number") or "this invoice"
    vend_name = evidence.get("invoice", {}).get("vendor_name") or "this vendor"

    cleaned_findings: List[FindingSchema] = []
    seen_keys = set()

    for f in review.findings:
        # Sanitize accusatory wording
        clean_evidence = sanitize_text(f.evidence)
        clean_explanation = sanitize_text(f.explanation)
        f_type_upper = (f.type or "").strip().upper()

        # Check for any duplicate-related findings from LLM
        is_dup_related = (
            "DUPLICATE" in f_type_upper or
            "duplicate" in clean_evidence.lower() or
            "duplicate" in clean_explanation.lower()
        )

        if is_dup_related:
            # Consolidate: skip LLM variations; we add one authoritative DUPLICATE_INVOICE finding below if genuine
            continue

        # Check for hallucinated price changes
        if f.type == "PRICE_CHANGE":
            prod_key = f.product.strip().lower() if f.product else ""
            if hist_status == "INSUFFICIENT_EVIDENCE" or prod_key not in valid_products:
                key = ("INSUFFICIENT_EVIDENCE", f.product)
                if key not in seen_keys:
                    seen_keys.add(key)
                    cleaned_findings.append(FindingSchema(
                        type="INSUFFICIENT_EVIDENCE",
                        severity="NONE",
                        product=f.product,
                        evidence="No prior comparable invoice data available for this product.",
                        explanation="Historical evidence is insufficient to verify unit price changes."
                    ))
                continue
            else:
                comp = valid_products[prod_key]
                pct_chg_avg = comp.get("percentage_change_from_average", 0.0)
                pct_chg_prev = comp.get("percentage_change_from_previous", 0.0)
                is_decrease = comp.get("is_price_decrease", False) or (pct_chg_prev < 0 and pct_chg_avg < 0)
                
                # A price decrease is informational; it must not carry HIGH or MEDIUM review severity
                severity = f.severity
                if is_decrease and severity in ("HIGH", "MEDIUM"):
                    severity = "LOW"
                    
                key = ("PRICE_CHANGE", comp.get("product"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    cleaned_findings.append(FindingSchema(
                        type="PRICE_CHANGE",
                        severity=severity,
                        product=comp.get("product"),
                        evidence=clean_evidence,
                        explanation=clean_explanation
                    ))
        else:
            key = (f.type, f.product)
            if key not in seen_keys:
                seen_keys.add(key)
                cleaned_findings.append(FindingSchema(
                    type=f.type,
                    severity=f.severity,
                    product=f.product,
                    evidence=clean_evidence,
                    explanation=clean_explanation
                ))
            
    # Add single consolidated, authoritative duplicate finding if this is a genuine duplicate
    if is_genuine_dup:
        cleaned_findings.append(FindingSchema(
            type="DUPLICATE_INVOICE",
            severity="HIGH",
            product=None,
            evidence=f"Invoice #{inv_num} from {vend_name} was previously processed in the system ({dup_count} prior record(s) detected).",
            explanation="Duplicate submission detected. Excluded from historical price baselines to prevent self-referential bias; requires human verification before payment approval to prevent double payment."
        ))

    # Check if financial discrepancy noted
    if not fin_val.get("total_consistent", True):
        has_fin_finding = any(f.type == "FINANCIAL_DISCREPANCY" for f in cleaned_findings)
        if not has_fin_finding:
            cleaned_findings.append(FindingSchema(
                type="FINANCIAL_DISCREPANCY",
                severity="HIGH",
                product=None,
                evidence=f"Total mismatch difference: {fin_val.get('difference', 0.0)}",
                explanation="Calculated total does not equal subtotal plus tax."
            ))

    # Determine status & recommendation based on configured business rules:
    # 1. Actionable price increases (significant or material increases exceeding thresholds)
    has_actionable_price_increase = any(
        (
            c.get("is_actionable_increase", False) or 
            c.get("change_category") in ("SIGNIFICANT_INCREASE", "MATERIAL_INCREASE") or
            (c.get("threshold_exceeded", False) and (
                c.get("percentage_change_from_previous", 0.0) > 0 or 
                c.get("percentage_change_from_average", 0.0) > 0
            ))
        )
        for c in hist_comparisons
    )
    
    # 2. Financial discrepancies
    has_financial_discrepancy = (
        fin_val.get("status") == "INVALID_DATA" or 
        not fin_val.get("total_consistent", True) or
        fin_val.get("has_negative_amounts", False) or
        fin_val.get("has_invalid_quantities", False) or
        fin_val.get("has_invalid_unit_prices", False)
    )
    
    # 3. Duplicate submissions
    has_duplicate = bool(hist_ctx.get("is_duplicate_invoice"))

    actionable_reasons: List[str] = []
    if has_financial_discrepancy:
        actionable_reasons.append("financial arithmetic discrepancy")
    if has_duplicate:
        actionable_reasons.append("duplicate invoice submission")
    if has_actionable_price_increase:
        actionable_reasons.append("unit price increase exceeding historical threshold")

    if actionable_reasons:
        final_status = "REVIEW_RECOMMENDED"
        final_rec = "REVIEW_RECOMMENDED"
    elif hist_status == "INSUFFICIENT_EVIDENCE":
        final_status = "INSUFFICIENT_EVIDENCE"
        final_rec = "INSUFFICIENT_DATA"
    else:
        final_status = "NORMAL"
        final_rec = "NO_ACTION_REQUIRED"

    clean_summary_explanation = sanitize_text(review.explanation)

    # Harmonize summary explanation with final recommendation:
    if final_rec == "NO_ACTION_REQUIRED":
        # Price decrease or normal variance must not leave conflicting recommendation text
        if "review recommended" in clean_summary_explanation.lower() or "requires review" in clean_summary_explanation.lower():
            clean_summary_explanation = (
                "Invoice passed financial validation. Any price change detected is an informational decrease "
                "or within standard tolerance; no verification action required."
            )
    elif final_rec == "REVIEW_RECOMMENDED":
        reasons_text = ", ".join(actionable_reasons)
        explanation_lower = clean_summary_explanation.lower()
        
        # If the explanation attributes review recommendation to missing historical context
        # rather than the genuine actionable reasons (e.g., duplicate submission, financial discrepancy):
        has_actionable_mention = any(
            term in explanation_lower 
            for term in ["duplicate", "discrepancy", "arithmetic", "price increase", "mismatch"]
        )
        attributes_to_missing_history = any(
            phrase in explanation_lower
            for phrase in [
                "historical context", 
                "historical data", 
                "insufficient historical", 
                "no historical baseline",
                "lack of historical",
                "absence of historical",
                "no prior"
            ]
        )
        
        if attributes_to_missing_history and not (has_duplicate and "duplicate" in explanation_lower):
            clean_summary_explanation = (
                f"Human review is recommended due to: {reasons_text}."
            )
            if hist_status == "INSUFFICIENT_EVIDENCE":
                clean_summary_explanation += (
                    " Note: Prior submission(s) are excluded from price comparisons to prevent self-referential bias; "
                    "insufficient historical baseline is an informational condition, not a cause for escalation."
                )
        elif not has_actionable_mention:
            clean_summary_explanation += f" Human review is recommended due to: {reasons_text}."

    return InvoiceReviewSchema(
        status=final_status,
        review_recommendation=final_rec,
        findings=cleaned_findings,
        explanation=clean_summary_explanation
    )

def review_invoice_with_llm(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stage 3: Evidence-Based LLM Review.
    Interprets deterministic evidence provided by Stage 1 and Stage 2 without inventing numbers.
    Protected by post-validation guardrails.
    """
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")
        
    client = groq.Groq(api_key=settings.GROQ_API_KEY)
    
    prompt = f"""
You are an AI Invoice Reviewer in Stage 3 of our invoice processing pipeline. 
Your job is to interpret the structured invoice data and deterministic analysis evidence provided below.

Strict Operational Rules:
1. Do NOT invent facts, historical prices, invoice counts, percentages, vendors, or amounts.
2. You must only reason from the evidence supplied by the backend.
3. If there is insufficient evidence to make a historical price comparison, output status INSUFFICIENT_EVIDENCE and state that.
4. Do not confuse unit price changes with quantity changes, tax changes, or discounts.
5. Do not flag price decreases as anomalies; report them neutrally.
6. A threshold for significant price change is roughly >10.0%. Material change is >25.0%.
7. The status should be 'NORMAL' if there are no significant anomalies.
8. NEVER label an invoice fraudulent, criminal, or a scam. Price increases must be described neutrally as business variances requiring human review.
9. Separate detected price changes (facts) from review recommendations (operational advice).

Evidence provided by Stage 1 (Extraction) and Stage 2 (Deterministic Analysis):
{json.dumps(evidence, indent=2)}

Produce a structured review with your findings, recommendation, and a brief objective explanation.
"""

    try:
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            response_format={
                "type": "json_schema", 
                "json_schema": {
                    "name": "invoice_review", 
                    "schema": InvoiceReviewSchema.model_json_schema(), 
                    "strict": True
                }
            },
            temperature=0.0
        )
        
        message_content = response.choices[0].message.content
        review = InvoiceReviewSchema.model_validate_json(message_content)
        validated_review = post_validate_review(review, evidence)
        return validated_review.model_dump()
    except Exception as e:
        logging.error(f"Groq API review failed: {e}")
        raise
