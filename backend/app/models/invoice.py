import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

class PipelineStatus(str, enum.Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    ANALYZING = "ANALYZING"
    REVIEWING = "REVIEWING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # These fields are optional because an invoice might just be uploaded
    # and not yet extracted. They will be populated later.
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    invoice_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    customer_name: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Financial fields mapped as Numeric to ensure exact precision (no float rounding errors)
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    
    # Required fields at the time of creation (upload)
    source_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    
    pipeline_status: Mapped[PipelineStatus] = mapped_column(
        Enum(PipelineStatus, name="pipelinestatus", create_constraint=True),
        default=PipelineStatus.PENDING,
        nullable=False,
        index=True
    )
    
    # Financial Validation (Stage 2)
    financial_validation: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Historical Context (Stage 2)
    historical_context: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # AI Review (Stage 3)
    review_result: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Pipeline Metadata
    extraction_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extraction_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    
    # Timezone-aware timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationship to items
    items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )

    # Unique constraint removed to allow duplicate uploads of the same invoice

    @property
    def extraction_metadata(self) -> Optional[dict]:
        if self.review_result and isinstance(self.review_result, dict):
            return self.review_result.get("extraction_metadata")
        if self.financial_validation and isinstance(self.financial_validation, dict):
            return self.financial_validation.get("extraction_metadata")
        return None

    @property
    def human_disposition(self) -> Optional[dict]:
        if self.review_result and isinstance(self.review_result, dict):
            return self.review_result.get("human_disposition")
        return None

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Description is required, the rest is optional depending on extraction quality
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # Percentage represented as decimal (e.g., 0.0825)
    line_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))

    # Relationship back to invoice
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")
