from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class ComparisonField(BaseModel):
    field_name: str
    llm_value: Any = None
    non_llm_value: Any = None
    matches: bool
    difference_note: Optional[str] = None

class ComparisonLineItem(BaseModel):
    index: int
    llm_item: Optional[Dict[str, Any]] = None
    non_llm_item: Optional[Dict[str, Any]] = None
    match_status: str  # EXACT_MATCH, PRICE_MISMATCH, QUANTITY_MISMATCH, ONLY_IN_LLM, ONLY_IN_NON_LLM
    difference_note: Optional[str] = None

class ExtractionMethodResult(BaseModel):
    method: str
    provenance: str
    processing_time_seconds: float
    success: bool
    is_experimental: bool = False
    error_message: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    financial_validation: Optional[Dict[str, Any]] = None
    verifiable_confidence: Optional[Dict[str, Any]] = None

class ExtractionComparisonResponse(BaseModel):
    invoice_id: int
    filename: str
    llm_result: ExtractionMethodResult
    non_llm_result: ExtractionMethodResult
    header_field_comparisons: List[ComparisonField]
    line_item_comparisons: List[ComparisonLineItem]
    summary_notes: List[str]
