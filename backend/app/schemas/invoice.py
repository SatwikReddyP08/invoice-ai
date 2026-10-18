from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from app.models.invoice import PipelineStatus

class InvoiceItemBase(BaseModel):
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    line_total: Optional[Decimal] = None

class InvoiceItemCreate(InvoiceItemBase):
    pass

class InvoiceItemUpdate(BaseModel):
    id: Optional[int] = None
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    line_total: Optional[Decimal] = None

class InvoiceItemResponse(InvoiceItemBase):
    id: int
    invoice_id: int

    model_config = ConfigDict(from_attributes=True)

class InvoiceBase(BaseModel):
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[datetime] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    source_file_path: str
    pipeline_status: PipelineStatus = PipelineStatus.PENDING

class InvoiceCreate(InvoiceBase):
    items: Optional[List[InvoiceItemCreate]] = []

class InvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[datetime] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    source_file_path: Optional[str] = None
    pipeline_status: Optional[PipelineStatus] = None
    items: Optional[List[InvoiceItemUpdate]] = None

class InvoiceResponse(InvoiceBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    financial_validation: Optional[dict] = None
    historical_context: Optional[dict] = None
    review_result: Optional[dict] = None
    
    extraction_started_at: Optional[datetime] = None
    extraction_completed_at: Optional[datetime] = None
    review_started_at: Optional[datetime] = None
    review_completed_at: Optional[datetime] = None
    
    extraction_metadata: Optional[dict] = None
    human_disposition: Optional[dict] = None
    
    items: List[InvoiceItemResponse] = []

    model_config = ConfigDict(from_attributes=True)
    
class InvoiceListResponse(BaseModel):
    items: List[InvoiceResponse]
    total: int
    skip: int
    limit: int

class ReviewDispositionRequest(BaseModel):
    disposition: str  # "ACKNOWLEDGED" | "NEEDS_FOLLOW_UP" | "RESOLVED"
    notes: Optional[str] = None

