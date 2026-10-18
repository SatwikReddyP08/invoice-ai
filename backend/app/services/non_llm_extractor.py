import os
import re
import time
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, List, Optional, Tuple
import fitz  # PyMuPDF
from pydantic import ValidationError

from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema

class NonLLMExtractionError(Exception):
    """Raised when Non-LLM extraction fails or encounters unsupported document types (e.g. scanned raster PDFs)."""
    pass

def parse_monetary_string(s: Optional[str]) -> Optional[float]:
    """Parse monetary string, stripping currency symbols and handling standard number formats."""
    if not s:
        return None
    # Remove currency symbols and non-numeric characters except . and ,
    clean = re.sub(r"[^\d.,]", "", str(s).strip())
    if not clean:
        return None
        
    # Handle European format (1.234,56) vs US format (1,234.56)
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    elif "," in clean:
        parts = clean.split(",")
        if len(parts) == 2 and len(parts[1]) in [1, 2]:
            clean = clean.replace(",", ".")
        else:
            clean = clean.replace(",", "")
            
    try:
        val = float(clean)
        return round(val, 2)
    except Exception:
        return None

def parse_date_string(s: Optional[str]) -> Optional[date]:
    """Parse dates in various standard formats."""
    if not s:
        return None
    clean = str(s).strip()
    
    date_patterns = [
        # 15 January 2026 or 15 Jan 2026
        (r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b", ["%d %B %Y", "%d %b %Y"]),
        # January 15, 2026 or Jan 15, 2026
        (r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})\b", ["%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y"]),
        # 2026-01-15 (ISO)
        (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", ["%Y-%m-%d"]),
        # 15/01/2026 or 01/15/2026
        (r"\b(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{4})\b", ["%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y"])
    ]
    
    for pat, formats in date_patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            matched_str = m.group(0).replace(",", "").strip()
            for fmt in formats:
                try:
                    return datetime.strptime(matched_str, fmt).date()
                except Exception:
                    continue
    return None

def extract_currency(text: str) -> Optional[str]:
    """Extract 3-letter currency code from symbols or text."""
    if re.search(r"\bINR\b|₹|Rs\.?", text, re.IGNORECASE):
        return "INR"
    if re.search(r"\bEUR\b|€", text, re.IGNORECASE):
        return "EUR"
    if re.search(r"\bUSD\b|\$", text, re.IGNORECASE):
        return "USD"
    if re.search(r"\bGBP\b|£", text, re.IGNORECASE):
        return "GBP"
    if re.search(r"\bCAD\b", text, re.IGNORECASE):
        return "CAD"
    if re.search(r"\bAUD\b", text, re.IGNORECASE):
        return "AUD"
    return None

def extract_customer_from_blocks(page_blocks: list, full_text: str) -> Optional[str]:
    """
    Extract customer name from 'Billed To', 'Bill To', or 'Customer' section
    using spatial block inspection and targeted textual patterns.
    """
    ignore_keywords = re.compile(
        r"\b(invoice|date|gstin|tax\s*id|pan|phone|tel|email|address|street|road|city|state|zip|pin|po\s*box|attn|subtotal|total|amount)\b",
        re.IGNORECASE
    )

    # 1. Spatial Block Inspection on Page 1
    if page_blocks and len(page_blocks) > 0:
        for b in page_blocks[0]:
            if len(b) < 5 or not isinstance(b[4], str):
                continue
            b_text = b[4].strip()
            lines = [l.strip() for l in b_text.splitlines() if l.strip()]
            for idx, line in enumerate(lines):
                if re.search(r"\b(billed\s*to|bill\s*to|invoice\s*to|invoiced\s*to|sold\s*to|customer|client)\b", line, re.IGNORECASE):
                    # Check if the name is on the same line after colon
                    same_line_parts = re.split(r"[:\-]", line, maxsplit=1)
                    if len(same_line_parts) > 1:
                        candidate = same_line_parts[1].strip()
                        if len(candidate) > 2 and not ignore_keywords.search(candidate):
                            return candidate
                    # Otherwise check subsequent lines in this block
                    for sub_line in lines[idx+1:idx+4]:
                        clean_sub = sub_line.strip()
                        if len(clean_sub) > 2 and not ignore_keywords.search(clean_sub):
                            return clean_sub

    # 2. Regex fallback over full document text
    patterns = [
        r"(?:Billed\s*To|Bill\s*To|Invoice\s*To|Invoiced\s*To|Customer|Client|Sold\s*To)[:\s\-]*\n\s*([A-Za-z0-9\s&.,'-]{3,60})",
        r"(?:Billed\s*To|Bill\s*To|Invoice\s*To|Invoiced\s*To|Customer|Client)[:\s]+([A-Za-z0-9\s&.,'-]{3,60})"
    ]
    for pat in patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).split("\n")[0].strip()
            if len(candidate) > 2 and not ignore_keywords.search(candidate):
                return candidate

    return None

def extract_tax_amounts(full_text: str, subtotal: Optional[float], total_amount: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """
    Extracts actual tax amount and tax rate while strictly distinguishing tax
    monetary lines from tax registration/identification numbers (e.g., GSTIN state codes, Tax ID, PAN).
    Returns (tax_amount, tax_rate).
    """
    tax_amount = None
    tax_rate = None

    # Step 1: Specifically search for combined or separate GST/VAT/Tax financial lines
    # Ensure tax identifiers (GSTIN, Tax ID, VAT No, PAN) are excluded by requiring the line to end in a valid monetary figure
    tax_line_patterns = [
        # Total Tax / Tax Amount / GST Amount / VAT Amount
        r"(?:Total\s*Tax|Tax\s*Amount|GST\s*Amount|VAT\s*Amount|Output\s*GST|Input\s*GST)[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)(?!\s*[A-Za-z0-9])",
        # GST with percentage: GST (18%), GST @ 18%, GST 18%
        r"(?:\bGST\b|\bTax\b|\bVAT\b|\bIGST\b)\s*(?:\(\s*(\d+(?:\.\d+)?)%\s*\)|\@\s*(\d+(?:\.\d+)?)%|\s*(\d+(?:\.\d+)?)%)?[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)(?!\s*[A-Za-z0-9])",
        # Generic Tax / VAT / GST without ID suffixes
        r"\b(?:GST|VAT|Tax)\b(?!\s*(?:IN|ID|No|Num|Reg|Registration))[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)(?!\s*[A-Za-z0-9])"
    ]

    for pat in tax_line_patterns:
        matches = list(re.finditer(pat, full_text, re.IGNORECASE))
        if matches:
            for m in matches:
                # Discard match if line contains GSTIN or Tax ID
                match_start = max(0, m.start() - 20)
                pre_ctx = full_text[match_start:m.start()].lower()
                if any(k in pre_ctx for k in ["gstin", "tax id", "vat no", "tin", "pan", "cin"]):
                    continue

                # Last group is the monetary amount
                amt_str = m.group(m.lastindex)
                parsed_amt = parse_monetary_string(amt_str)
                if parsed_amt is not None and parsed_amt > 0:
                    tax_amount = parsed_amt
                    # Check if a percentage was matched
                    for g in m.groups()[:-1]:
                        if g and parse_monetary_string(g):
                            p = parse_monetary_string(g)
                            tax_rate = round(p / 100.0, 4)
                            break
                    break
        if tax_amount is not None:
            break

    # Step 2: Check for separate CGST + SGST lines (e.g. Indian intra-state GST)
    if tax_amount is None:
        cgst_m = re.search(r"\bCGST\b[^:\n]*[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)(?!\s*[A-Za-z0-9])", full_text, re.IGNORECASE)
        sgst_m = re.search(r"\bSGST\b[^:\n]*[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,]+(?:\.\d{1,2})?)(?!\s*[A-Za-z0-9])", full_text, re.IGNORECASE)
        if cgst_m and sgst_m:
            cgst_val = parse_monetary_string(cgst_m.group(1))
            sgst_val = parse_monetary_string(sgst_m.group(1))
            if cgst_val is not None and sgst_val is not None:
                tax_amount = round(cgst_val + sgst_val, 2)

    # Step 3: Arithmetic verification & reconciliation against Subtotal and Total
    if subtotal is not None and total_amount is not None and total_amount >= subtotal:
        expected_tax = round(total_amount - subtotal, 2)
        if tax_amount is None:
            # If tax was not explicitly parsed or was masked, but subtotal and total balance, verify expected tax
            tax_amount = expected_tax
        elif abs((subtotal + tax_amount) - total_amount) > 0.05:
            # If the parsed tax amount does not reconcile (e.g. caught a state code or line number),
            # check if expected_tax exists in text or reconciles cleanly
            if abs((subtotal + expected_tax) - total_amount) < 0.01:
                # Check if expected_tax or formatted expected_tax exists in document text
                exp_str = f"{expected_tax:,.2f}"
                exp_str_alt = f"{expected_tax:.2f}"
                if exp_str in full_text or exp_str_alt in full_text:
                    tax_amount = expected_tax

    return tax_amount, tax_rate

def extract_items_from_coordinate_clustering(pages_words: list, full_text: str) -> List[InvoiceItemExtractionSchema]:
    """
    Deterministic spatial line clustering parser.
    Groups word spans by y-coordinates into horizontal lines, isolates the table region
    between header and footer, parses description, quantity, unit price, and line total,
    and supports multi-line wrapped cell descriptions.
    """
    items: List[InvoiceItemExtractionSchema] = []

    header_keywords = ["description", "item", "particulars", "service", "details"]
    col_keywords = ["qty", "quantity", "hrs", "hours", "units", "rate", "price", "amount", "total"]
    footer_keywords = ["subtotal", "sub total", "total tax", "tax amount", "grand total", "total amount", "amount in words", "payment terms", "bank details"]

    for page_idx, words in enumerate(pages_words):
        if not words:
            continue

        # Group words into lines by y-coordinate (tolerance: ±3 points)
        lines_dict = {}
        for w in words:
            x0, y0, x1, y1, text, block_no, line_no, word_no = w
            # Find an existing line within y tolerance
            assigned_y = None
            for existing_y in lines_dict.keys():
                if abs(y0 - existing_y) <= 3.5:
                    assigned_y = existing_y
                    break
            if assigned_y is None:
                assigned_y = y0
                lines_dict[assigned_y] = []
            lines_dict[assigned_y].append(w)

        # Sort visual lines by y-coordinate
        sorted_y = sorted(lines_dict.keys())
        visual_lines = []
        for y in sorted_y:
            # Sort words in line from left to right by x0
            line_words = sorted(lines_dict[y], key=lambda item: item[0])
            visual_lines.append((y, line_words))

        # Find header line index
        header_line_idx = -1
        for idx, (y, line_words) in enumerate(visual_lines):
            line_str = " ".join(w[4].lower() for w in line_words)
            has_desc = any(k in line_str for k in header_keywords)
            has_cols = any(k in line_str for k in col_keywords)
            if has_desc and has_cols:
                header_line_idx = idx
                break

        if header_line_idx == -1:
            continue

        # Find footer line index
        footer_line_idx = len(visual_lines)
        for idx in range(header_line_idx + 1, len(visual_lines)):
            y, line_words = visual_lines[idx]
            line_str = " ".join(w[4].lower() for w in line_words)
            if any(k in line_str for k in footer_keywords):
                footer_line_idx = idx
                break

        # Process lines within the table band
        current_item = None
        for idx in range(header_line_idx + 1, footer_line_idx):
            y, line_words = visual_lines[idx]
            tokens = [w[4].strip() for w in line_words if w[4].strip()]
            if not tokens:
                continue

            # Look for monetary/numeric values from right to left
            numeric_indices = []
            for t_idx, token in enumerate(tokens):
                cleaned = re.sub(r"[^\d.,]", "", token)
                if cleaned and any(char.isdigit() for char in cleaned):
                    val = parse_monetary_string(token)
                    if val is not None:
                        numeric_indices.append((t_idx, val))

            # Case A: Line item with at least 2 numeric values (Qty + Total or Price + Total)
            if len(numeric_indices) >= 2:
                # Rightmost token is total amount
                tot_idx, tot_val = numeric_indices[-1]
                # Second to right is price or rate
                price_idx, price_val = numeric_indices[-2]
                
                qty_val = 1.0
                if len(numeric_indices) >= 3:
                    qty_idx, qty_val = numeric_indices[-3]
                elif price_val > 0 and tot_val > 0:
                    calculated_qty = round(tot_val / price_val, 2)
                    if calculated_qty in [1.0, 2.0, 3.0, 4.0, 5.0, 10.0]:
                        qty_val = calculated_qty

                # Description is everything to the left of the first numeric index used
                first_num_idx = numeric_indices[-3][0] if len(numeric_indices) >= 3 else price_idx
                desc_tokens = tokens[:first_num_idx]
                desc_text = " ".join(desc_tokens).strip()

                if desc_text:
                    current_item = InvoiceItemExtractionSchema(
                        description=desc_text,
                        quantity=qty_val,
                        unit_price=price_val,
                        tax_rate=None,
                        line_total=tot_val
                    )
                    items.append(current_item)
            elif len(numeric_indices) == 0:
                # Case B: Multi-line wrapped description continuation
                continuation_text = " ".join(tokens).strip()
                if items and len(continuation_text) > 1:
                    # Append continuation text to previous line item description
                    items[-1].description = f"{items[-1].description} {continuation_text}".strip()

    return items

def extract_non_llm(file_path: str) -> Tuple[InvoiceExtractionSchema, Dict[str, Any]]:
    """
    Production Non-LLM Invoice Extraction Service.
    Uses PyMuPDF deterministic layout analysis, spatial coordinate table parsing,
    multi-line wrapped cell merging, multi-page table spanning, and arithmetic validation.
    
    Returns:
        Tuple[InvoiceExtractionSchema, Dict[str, Any]]: Validated extraction schema + extraction metadata.
    """
    start_time = time.time()
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Invoice file not found: {file_path}")
        
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise NonLLMExtractionError(f"Failed to open document: {str(e)}")
        
    full_text = ""
    pages_words = []
    pages_tables = []
    page_blocks = []
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        txt = page.get_text()
        full_text += f"\n--- Page {page_idx+1} ---\n" + txt
        words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
        pages_words.append(words)
        blocks = page.get_text("blocks")
        page_blocks.append(blocks)
        
        # Try finding tables with default strategy, and fallback to text strategy
        tbls = None
        try:
            tbls = page.find_tables()
            if not tbls or not tbls.tables:
                tbls = page.find_tables(vertical_strategy="text")
        except Exception:
            tbls = None
        pages_tables.append(tbls)
            
    # Check for scanned raster PDF (zero text words)
    total_words = sum(len(w) for w in pages_words)
    if total_words == 0:
        doc.close()
        raise NonLLMExtractionError(
            "Scanned raster PDF detected: Document contains no embedded digital text. "
            "Non-LLM extraction requires digital text. Please use LLM-assisted extraction "
            "(which supports visual document understanding) or provide an OCR-processed document."
        )
        
    # 1. Invoice Number Extraction
    invoice_number = None
    inv_patterns = [
        r"(?:Invoice\s*(?:Number|No|Ref|#|ID)?[:\s#]+)([A-Z0-9_\-\/]{3,30})",
        r"(?:Bill\s*(?:Number|No|#)?[:\s#]+)([A-Z0-9_\-\/]{3,30})",
        r"\b([A-Z]{2,4}-\d{4}-\d{3,5})\b",
        r"\b(INV-[A-Z0-9_\-]+)\b"
    ]
    for pat in inv_patterns:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if not re.search(r"^(date|total|amount|due|tax)$", candidate, re.IGNORECASE):
                invoice_number = candidate
                break
                
    # 2. Invoice Date Extraction
    invoice_date = None
    date_match_res = re.search(r"(?:Invoice\s*Date|Bill\s*Date|Date\s*of\s*Issue|Date)[:\s]+([^\n\r]+)", full_text, re.IGNORECASE)
    if date_match_res:
        invoice_date = parse_date_string(date_match_res.group(1))
    if not invoice_date:
        invoice_date = parse_date_string(full_text)
        
    # 3. Currency Extraction
    currency = extract_currency(full_text)
    
    # 4. Vendor Name Extraction
    vendor_name = None
    vend_m = re.search(r"(?:Vendor|Billed By\s*\(Vendor\)|Supplier|Seller|From)[:\s\n]+([A-Z0-9\s&.,'-]+?)(?:\n\n|\n[A-Z\s]+:|Customer|Billed To|Ship To|Workplace|\Z)", full_text, re.IGNORECASE)
    if vend_m:
        vendor_candidate = vend_m.group(1).split("\n")[0].strip()
        if len(vendor_candidate) > 2 and not re.search(r"Invoice|Tax|Date", vendor_candidate, re.IGNORECASE):
            vendor_name = vendor_candidate
            
    if not vendor_name and len(page_blocks) > 0 and len(page_blocks[0]) > 0:
        # Fallback to top visual block on page 1
        for b in page_blocks[0][:4]:
            if len(b) < 5 or not isinstance(b[4], str):
                continue
            b_text = b[4].strip()
            lines = [l.strip() for l in b_text.splitlines() if len(l.strip()) > 2]
            for l in lines:
                if not re.search(r"invoice|tax|original|copy|recipient|page|date|bill\s*to", l, re.IGNORECASE) and len(l) > 3:
                    vendor_name = l
                    break
            if vendor_name:
                break
                
    # 5. Customer Name Extraction
    customer_name = extract_customer_from_blocks(page_blocks, full_text)
            
    # 6. Financial Summary (Subtotal, Total, and Tax)
    subtotal = None
    sub_m = re.search(r"(?:Subtotal|Sub\s*Total|Taxable\s*Amount|Net\s*Amount)[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)", full_text, re.IGNORECASE)
    if sub_m:
        subtotal = parse_monetary_string(sub_m.group(1))

    total_amount = None
    tot_m = re.search(r"(?:(?<!Sub)\bTotal(?:\s*Amount)?(?:\s*Payable)?|Grand\s*Total|Invoice\s*Total|Balance\s*Due|Total Due)[:\s]+(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)", full_text, re.IGNORECASE)
    if tot_m:
        total_amount = parse_monetary_string(tot_m.group(1))

    tax_amount, tax_rate = extract_tax_amounts(full_text, subtotal, total_amount)
        
    # 7. Line Item Extraction (Method A: PyMuPDF Table Finder)
    items: List[InvoiceItemExtractionSchema] = []
    active_column_mapping: Optional[Dict[str, int]] = None
    
    for page_idx, tbls in enumerate(pages_tables):
        if not tbls or not tbls.tables:
            continue
            
        for t in tbls.tables:
            raw_rows = t.extract()
            if not raw_rows:
                continue
                
            start_row_idx = 0
            # Inspect first row for column headers
            header = [str(c).lower().strip() if c else "" for c in raw_rows[0]]
            
            desc_col = -1
            qty_col = -1
            price_col = -1
            tax_col = -1
            tot_col = -1
            
            for col_idx, col_name in enumerate(header):
                if any(k in col_name for k in ["desc", "item", "product", "particulars", "details", "service"]):
                    desc_col = col_idx
                elif any(k in col_name for k in ["qty", "quantity", "units", "hrs", "hours", "count"]):
                    qty_col = col_idx
                elif any(k in col_name for k in ["price", "rate", "cost", "unit"]):
                    price_col = col_idx
                elif any(k in col_name for k in ["tax", "vat", "gst", "igst", "cgst"]):
                    tax_col = col_idx
                elif any(k in col_name for k in ["total", "amount", "line"]):
                    tot_col = col_idx
                    
            if desc_col >= 0:
                # Valid header identified on this page
                active_column_mapping = {
                    "desc": desc_col,
                    "qty": qty_col,
                    "price": price_col,
                    "tax": tax_col,
                    "total": tot_col
                }
                start_row_idx = 1
            elif active_column_mapping is not None and len(raw_rows[0]) >= 3:
                # Multi-page table continuation: reuse active column mapping from previous page
                desc_col = active_column_mapping["desc"]
                qty_col = active_column_mapping["qty"]
                price_col = active_column_mapping["price"]
                tax_col = active_column_mapping["tax"]
                tot_col = active_column_mapping["total"]
                start_row_idx = 0
            else:
                continue
                
            for row in raw_rows[start_row_idx:]:
                if not row or len(row) <= desc_col:
                    continue
                    
                raw_desc = str(row[desc_col] or "").strip()
                if not raw_desc:
                    continue
                    
                # Skip summary footer rows inside table
                if any(k in raw_desc.lower() for k in ["subtotal", "total", "tax", "vat", "gst", "amount in words"]):
                    continue
                    
                desc_clean = raw_desc.replace("\n", " ").strip()
                
                qty_val = parse_monetary_string(row[qty_col]) if qty_col >= 0 and len(row) > qty_col and row[qty_col] else None
                price_val = parse_monetary_string(row[price_col]) if price_col >= 0 and len(row) > price_col and row[price_col] else None
                tot_val = parse_monetary_string(row[tot_col]) if tot_col >= 0 and len(row) > tot_col and row[tot_col] else None
                
                tax_rate_val = None
                if tax_col >= 0 and len(row) > tax_col and row[tax_col]:
                    tax_num = parse_monetary_string(str(row[tax_col]))
                    if tax_num is not None:
                        tax_rate_val = tax_num / 100.0 if tax_num > 1.0 else tax_num
                        
                # Multi-line cell merging
                if qty_val is None and price_val is None and tot_val is None:
                    if len(items) > 0:
                        items[-1].description = f"{items[-1].description} {desc_clean}".strip()
                    continue
                    
                # Arithmetic reconciliation for line items
                if tot_val is None and qty_val is not None and price_val is not None:
                    tot_val = round(qty_val * price_val, 2)
                elif price_val is None and tot_val is not None and qty_val is not None and qty_val > 0:
                    price_val = round(tot_val / qty_val, 2)
                    
                items.append(InvoiceItemExtractionSchema(
                    description=desc_clean,
                    quantity=qty_val,
                    unit_price=price_val,
                    tax_rate=tax_rate_val,
                    line_total=tot_val
                ))

    # Method B: Spatial coordinate clustering if table finder yielded 0 items
    if not items:
        items = extract_items_from_coordinate_clustering(pages_words, full_text)

    # Method C: Flexible line regex fallback if previous methods yielded 0 items
    if not items:
        # Matches both 4-column and 5-column formats, with optional currency symbols
        item_line_patterns = [
            # 5-column: Desc + Qty + Price + Tax% + Total
            re.compile(
                r"^(?:(?:\d+[\.\)]|\*|-)\s+)?([A-Za-z0-9\s()\"'\/&.,-]{3,60}?)\s{2,}(\d+(?:\.\d+)?)\s{2,}(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)\s{2,}(\d+(?:\.\d+)?%?)\s{2,}(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)",
                re.MULTILINE
            ),
            # 4-column: Desc + Qty + Price + Total
            re.compile(
                r"^(?:(?:\d+[\.\)]|\*|-)\s+)?([A-Za-z0-9\s()\"'\/&.,-]{3,60}?)\s{2,}(\d+(?:\.\d+)?)\s{2,}(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)\s{2,}(?:[A-Z]{3}|[$€£₹]|Rs\.?)?\s*([\d,.]+)",
                re.MULTILINE
            )
        ]
        for pattern in item_line_patterns:
            for m in pattern.finditer(full_text):
                desc = m.group(1).strip()
                if any(k in desc.lower() for k in ["total", "subtotal", "tax", "vat", "gst", "balance"]):
                    continue
                qty = parse_monetary_string(m.group(2))
                price = parse_monetary_string(m.group(3))
                
                if m.lastindex == 5:
                    tax_str = m.group(4)
                    tax_r = parse_monetary_string(tax_str) / 100.0 if tax_str else None
                    tot = parse_monetary_string(m.group(5))
                else:
                    tax_r = None
                    tot = parse_monetary_string(m.group(4))

                if tot is None and qty is not None and price is not None:
                    tot = round(qty * price, 2)
                    
                items.append(InvoiceItemExtractionSchema(
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    tax_rate=tax_r,
                    line_total=tot
                ))
            if items:
                break

    doc.close()

    # Deterministic Arithmetic Reconciliation on Header Totals
    calc_subtotal = round(sum(it.line_total for it in items if it.line_total is not None), 2) if items else None
    if subtotal is None and calc_subtotal is not None and calc_subtotal > 0:
        subtotal = calc_subtotal
        
    if total_amount is None:
        if subtotal is not None and tax_amount is not None:
            total_amount = round(subtotal + tax_amount, 2)
        elif subtotal is not None:
            total_amount = subtotal
            
    if tax_amount is None and total_amount is not None and subtotal is not None and total_amount >= subtotal:
        tax_amount = round(total_amount - subtotal, 2)

    # Verifiable Confidence & Integrity Assessment
    elapsed = round(time.time() - start_time, 4)
    
    math_consistent = False
    if total_amount is not None and subtotal is not None:
        math_consistent = abs((subtotal + (tax_amount or 0.0)) - total_amount) < 0.05
        
    valid_items_math = 0
    for it in items:
        if it.quantity is not None and it.unit_price is not None and it.line_total is not None:
            if abs((it.quantity * it.unit_price) - it.line_total) < 0.05:
                valid_items_math += 1
    items_math_rate = round(valid_items_math / len(items), 2) if items else 0.0

    # Fields Requiring Verification & Completeness Tiering
    fields_requiring_verification: List[str] = []
    if not invoice_number:
        fields_requiring_verification.append("invoice_number")
    if not invoice_date:
        fields_requiring_verification.append("invoice_date")
    if not vendor_name:
        fields_requiring_verification.append("vendor_name")
    if not customer_name:
        fields_requiring_verification.append("customer_name")
    if not items:
        fields_requiring_verification.append("line_items")
    if not math_consistent:
        fields_requiring_verification.append("arithmetic_balance")

    if not invoice_number and not total_amount and not items:
        completeness_status = "FAILED_OR_UNSUPPORTED"
    elif len(fields_requiring_verification) == 0 and math_consistent and len(items) > 0:
        completeness_status = "EXTRACTION_COMPLETE"
    else:
        completeness_status = "NEEDS_VERIFICATION"
    
    metadata = {
        "extraction_method": "NON_LLM",
        "provenance": "PyMuPDF Deterministic Layout, Coordinate Table & Spatial Parser",
        "processing_time_seconds": elapsed,
        "is_experimental": True,
        "completeness_status": completeness_status,
        "fields_requiring_verification": fields_requiring_verification,
        "verifiable_confidence": {
            "math_consistent": math_consistent,
            "items_multiplication_valid_rate": items_math_rate,
            "has_invoice_number": bool(invoice_number),
            "has_invoice_date": bool(invoice_date),
            "has_vendor_name": bool(vendor_name),
            "has_customer_name": bool(customer_name),
            "has_total_amount": bool(total_amount),
            "line_item_count": len(items)
        }
    }

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
        return extracted_schema, metadata
    except ValidationError as e:
        raise NonLLMExtractionError(f"Extracted data failed schema validation: {str(e)}")
