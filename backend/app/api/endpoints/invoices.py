from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Any, Optional
import os

from app.core.database import get_db
from app.crud import crud_invoice
from app.models.invoice import PipelineStatus
from app.schemas.invoice import (
    InvoiceCreate, 
    InvoiceUpdate, 
    InvoiceResponse, 
    InvoiceListResponse,
    ReviewDispositionRequest
)
from app.schemas.upload import UploadResponse
from app.services.upload_service import save_upload_file
from app.services.ai_extractor import extract_invoice
from app.services.financial_analysis import analyze_financials
from app.services.historical_analysis import analyze_history
from app.services.ai_review import review_invoice_with_llm
from app.services.extraction_dispatcher import dispatch_extraction, run_extraction_comparison
from app.services.non_llm_extractor import NonLLMExtractionError
from app.schemas.comparison import ExtractionComparisonResponse
from app.core.config import settings
from datetime import datetime, timezone

router = APIRouter()

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def upload_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Any:
    """Upload an invoice document and create an initial DB record."""
    try:
        file_info = save_upload_file(file)
    except Exception as e:
        # If it's an HTTPException (like 400 or 413), re-raise it
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))
        
    # Integrate with DB
    invoice_in = InvoiceCreate(source_file_path=file_info["stored_filename"])
    
    try:
        invoice = crud_invoice.create_invoice(db=db, invoice_in=invoice_in)
        return UploadResponse(
            invoice_id=invoice.id,
            original_filename=file_info["filename"],
            stored_filename=file_info["stored_filename"],
            mime_type=file_info["mime_type"],
            size=file_info["size"],
            status=invoice.pipeline_status.value
        )
    except Exception as e:
        if os.path.exists(file_info["file_path"]):
            os.remove(file_info["file_path"])
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(invoice_in: InvoiceCreate, db: Session = Depends(get_db)) -> Any:
    """Create new invoice."""
    invoice = crud_invoice.create_invoice(db=db, invoice_in=invoice_in)
    return invoice

@router.get("/", response_model=InvoiceListResponse)
def read_invoices(
    skip: int = 0, 
    limit: int = 100, 
    review_filter: Optional[str] = Query(None, description="Filter invoices: 'all', 'needs_attention', 'completed', 'informational'"),
    db: Session = Depends(get_db)
) -> Any:
    """Retrieve invoices with optional review queue filtering."""
    invoices, total = crud_invoice.get_invoices(db=db, skip=skip, limit=limit, review_filter=review_filter)
    return InvoiceListResponse(items=invoices, total=total, skip=skip, limit=limit)

@router.get("/{invoice_id}", response_model=InvoiceResponse)
def read_invoice(invoice_id: int, db: Session = Depends(get_db)) -> Any:
    """Get invoice by ID."""
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@router.put("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: int, invoice_in: InvoiceUpdate, db: Session = Depends(get_db)) -> Any:
    """Update an invoice."""
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = crud_invoice.update_invoice(db=db, db_invoice=invoice, invoice_in=invoice_in)
    return invoice

@router.post("/{invoice_id}/extract", response_model=InvoiceResponse)
def extract_invoice_data(
    invoice_id: int, 
    mode: str = "llm",
    db: Session = Depends(get_db)
) -> Any:
    """Extract data from uploaded invoice document using selectable mode ('llm' or 'non_llm')."""
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    file_path = os.path.join(settings.STORAGE_DIR, invoice.source_file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Invoice source file not found")
        
    # If we already have extracted data but reviewing failed, we could allow skipping extraction.
    # But for simplicity, if it's PENDING or FAILED, we do the full pipeline.
    if invoice.pipeline_status in (PipelineStatus.EXTRACTING, PipelineStatus.ANALYZING, PipelineStatus.REVIEWING):
        raise HTTPException(status_code=400, detail="Invoice is currently being processed")
        
    # Check if Stage 1 extraction was previously completed successfully and can be reused
    has_prior_successful_extraction = (
        invoice.extraction_completed_at is not None and
        invoice.vendor_name is not None and
        len(invoice.items) > 0
    )

    extracted_data = None
    extraction_meta = None
    if not has_prior_successful_extraction and invoice.pipeline_status in (PipelineStatus.PENDING, PipelineStatus.FAILED):
        try:
            # STAGE 1 — Extraction via Dispatcher (LLM-assisted or Non-LLM)
            invoice.pipeline_status = PipelineStatus.EXTRACTING
            invoice.extraction_started_at = datetime.now(timezone.utc)
            db.commit()
            
            extracted_data, extraction_meta = dispatch_extraction(file_path, mode=mode)
            invoice.extraction_completed_at = datetime.now(timezone.utc)
            
            # Save Stage 1 results immediately so they are persisted if Stage 3 fails later
            items_data = [item.model_dump() for item in extracted_data.items] if extracted_data.items else []
            update_data = InvoiceUpdate(
                invoice_number=extracted_data.invoice_number,
                vendor_name=extracted_data.vendor_name,
                invoice_date=extracted_data.invoice_date,
                customer_name=extracted_data.customer_name,
                subtotal=extracted_data.subtotal,
                tax_amount=extracted_data.tax_amount,
                total_amount=extracted_data.total_amount,
                currency=extracted_data.currency,
                pipeline_status=PipelineStatus.EXTRACTING,
                items=items_data
            )
            invoice = crud_invoice.update_invoice(db=db, db_invoice=invoice, invoice_in=update_data)
        except NonLLMExtractionError as e:
            db.rollback()
            invoice.pipeline_status = PipelineStatus.FAILED
            db.commit()
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            db.rollback()
            invoice.pipeline_status = PipelineStatus.FAILED
            db.commit()
            raise HTTPException(status_code=500, detail=f"Stage 1 Extraction failed: {str(e)}")

    # If Stage 1 was skipped on retry, reconstruct extracted_data from the existing DB record
    if extracted_data is None:
        from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema
        extracted_data = InvoiceExtractionSchema(
            invoice_number=invoice.invoice_number,
            vendor_name=invoice.vendor_name,
            invoice_date=invoice.invoice_date.date() if isinstance(invoice.invoice_date, datetime) else invoice.invoice_date,
            customer_name=invoice.customer_name,
            subtotal=float(invoice.subtotal) if invoice.subtotal else None,
            tax_amount=float(invoice.tax_amount) if invoice.tax_amount else None,
            total_amount=float(invoice.total_amount) if invoice.total_amount else None,
            currency=invoice.currency,
            items=[InvoiceItemExtractionSchema(
                description=item.description,
                quantity=float(item.quantity) if item.quantity is not None else None,
                unit_price=float(item.unit_price) if item.unit_price is not None else None,
                tax_rate=float(item.tax_rate) if item.tax_rate is not None else None,
                line_total=float(item.line_total) if item.line_total is not None else None
            ) for item in invoice.items]
        )

    try:
        # STAGE 2 — DETERMINISTIC
        invoice.pipeline_status = PipelineStatus.ANALYZING
        db.commit()
        
        financial_analysis = analyze_financials(extracted_data)
        historical_context = analyze_history(db, extracted_data, invoice.id)
        
        if extraction_meta:
            financial_analysis["extraction_metadata"] = extraction_meta

        invoice.financial_validation = financial_analysis
        invoice.historical_context = historical_context
        db.commit()
        
        # STAGE 3 — AI Review (remains LLM-based for both modes)
        invoice.pipeline_status = PipelineStatus.REVIEWING
        invoice.review_started_at = datetime.now(timezone.utc)
        db.commit()
        
        evidence = {
            "invoice": extracted_data.model_dump(mode='json'),
            "financial_validation": financial_analysis,
            "historical_context": historical_context
        }
        review_result = review_invoice_with_llm(evidence)
        invoice.review_completed_at = datetime.now(timezone.utc)
        
        if extraction_meta:
            review_result["extraction_metadata"] = extraction_meta

        # STAGE 4 — PERSIST Final state
        invoice.review_result = review_result
        invoice.pipeline_status = PipelineStatus.SUCCESS
        db.commit()
        db.refresh(invoice)
        
        return invoice
    except Exception as e:
        db.rollback()
        invoice.pipeline_status = PipelineStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"Pipeline failed at Stage 2/3: {str(e)}")

@router.post("/{invoice_id}/compare", response_model=ExtractionComparisonResponse)
def compare_invoice_extraction(invoice_id: int, db: Session = Depends(get_db)) -> Any:
    """
    Run side-by-side comparison of LLM-assisted vs. Non-LLM extraction on the document.
    Does not create duplicate database records or alter historical baselines.
    """
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    file_path = os.path.join(settings.STORAGE_DIR, invoice.source_file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Invoice source file not found")
        
    try:
        comparison_res = run_extraction_comparison(file_path=file_path, invoice_id=invoice_id)
        return comparison_res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")

@router.post("/{invoice_id}/disposition", response_model=InvoiceResponse)
def set_invoice_disposition(
    invoice_id: int,
    payload: ReviewDispositionRequest,
    db: Session = Depends(get_db)
) -> Any:
    """
    Record a human reviewer disposition (ACKNOWLEDGED, NEEDS_FOLLOW_UP, or RESOLVED)
    with optional notes. Preserves all underlying findings and AI review.
    """
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    valid_dispositions = ["ACKNOWLEDGED", "NEEDS_FOLLOW_UP", "RESOLVED"]
    disp_upper = (payload.disposition or "").strip().upper()
    if disp_upper not in valid_dispositions:
        raise HTTPException(
            status_code=422, 
            detail=f"Invalid disposition '{payload.disposition}'. Must be one of: {', '.join(valid_dispositions)}"
        )
        
    if not invoice.review_result or not isinstance(invoice.review_result, dict):
        invoice.review_result = {}
        
    invoice.review_result["human_disposition"] = {
        "disposition": disp_upper,
        "notes": (payload.notes or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    flag_modified(invoice, "review_result")
    db.commit()
    db.refresh(invoice)
    return invoice

@router.get("/{invoice_id}/report")
def get_invoice_review_report(
    invoice_id: int,
    db: Session = Depends(get_db)
) -> Any:
    """
    Generate a downloadable comprehensive invoice audit and review report.
    Contains extracted details, extraction method, financial validation,
    historical price findings, AI review, and human disposition.
    """
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    review_res = invoice.review_result or {}
    fin_val = invoice.financial_validation or {}
    hist_ctx = invoice.historical_context or {}
    extraction_meta = invoice.extraction_metadata or {}
    human_disp = review_res.get("human_disposition")
    
    report = {
        "report_title": f"InVoice AI Audit & Review Report - #{invoice.invoice_number or invoice.id}",
        "report_generated_at": datetime.now(timezone.utc).isoformat(),
        "invoice_id": invoice.id,
        "invoice_summary": {
            "invoice_number": invoice.invoice_number,
            "vendor_name": invoice.vendor_name,
            "customer_name": invoice.customer_name,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "currency": invoice.currency,
            "subtotal": float(invoice.subtotal) if invoice.subtotal is not None else None,
            "tax_amount": float(invoice.tax_amount) if invoice.tax_amount is not None else None,
            "total_amount": float(invoice.total_amount) if invoice.total_amount is not None else None,
            "pipeline_status": invoice.pipeline_status.value
        },
        "line_items": [
            {
                "description": item.description,
                "quantity": float(item.quantity) if item.quantity is not None else None,
                "unit_price": float(item.unit_price) if item.unit_price is not None else None,
                "tax_rate": float(item.tax_rate) if item.tax_rate is not None else None,
                "line_total": float(item.line_total) if item.line_total is not None else None
            }
            for item in invoice.items
        ],
        "extraction_provenance": {
            "method": extraction_meta.get("extraction_method", "LLM_ASSISTED"),
            "provenance": extraction_meta.get("provenance", "Groq Vision API"),
            "processing_time_seconds": extraction_meta.get("processing_time_seconds"),
            "completeness_status": extraction_meta.get("completeness_status", "EXTRACTION_COMPLETE"),
            "fields_requiring_verification": extraction_meta.get("fields_requiring_verification", [])
        },
        "financial_validation": {
            "total_consistent": fin_val.get("total_consistent"),
            "subtotal": fin_val.get("subtotal"),
            "tax_amount": fin_val.get("tax_amount"),
            "total_amount": fin_val.get("total_amount"),
            "calculated_total": fin_val.get("calculated_total"),
            "difference": fin_val.get("difference"),
            "line_items_count": len(invoice.items)
        },
        "historical_price_analysis": {
            "status": hist_ctx.get("status"),
            "total_historical_invoices": hist_ctx.get("total_historical_invoices", 0),
            "is_duplicate_invoice": hist_ctx.get("is_duplicate_invoice", False),
            "comparisons": hist_ctx.get("historical_comparisons", [])
        },
        "ai_review": {
            "review_recommendation": review_res.get("review_recommendation", "NO_ACTION_REQUIRED"),
            "pipeline_status": review_res.get("status", "NORMAL"),
            "findings": review_res.get("findings", []),
            "overall_decision_explanation": review_res.get("explanation", "")
        },
        "human_reviewer_disposition": human_disp if human_disp else {
            "status": "PENDING_REVIEW" if review_res.get("review_recommendation") == "REVIEW_RECOMMENDED" else "INFORMATIONAL_NOT_REVIEWED",
            "disposition": None,
            "notes": None,
            "updated_at": None
        }
    }
    return report

@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)) -> None:
    """Delete an invoice."""
    invoice = crud_invoice.get_invoice(db=db, invoice_id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    crud_invoice.delete_invoice(db=db, db_invoice=invoice)
    return None

