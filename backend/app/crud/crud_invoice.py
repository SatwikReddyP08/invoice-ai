from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Tuple, Optional
from app.models.invoice import Invoice, InvoiceItem
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate



def get_invoice(db: Session, invoice_id: int) -> Optional[Invoice]:
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()

def get_invoices(db: Session, skip: int = 0, limit: int = 100, review_filter: Optional[str] = None) -> Tuple[List[Invoice], int]:
    all_invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    
    if not review_filter or review_filter == "all":
        filtered = all_invoices
    elif review_filter == "needs_attention":
        filtered = []
        for inv in all_invoices:
            rr = inv.review_result or {}
            rec = rr.get("review_recommendation")
            disp = rr.get("human_disposition", {}).get("disposition") if rr.get("human_disposition") else None
            if rec == "REVIEW_RECOMMENDED" and disp != "RESOLVED":
                filtered.append(inv)
    elif review_filter == "completed":
        filtered = [
            inv for inv in all_invoices 
            if inv.review_result and inv.review_result.get("human_disposition")
        ]
    elif review_filter == "informational":
        filtered = [
            inv for inv in all_invoices 
            if inv.review_result and inv.review_result.get("review_recommendation") in ("NO_ACTION_REQUIRED", "INSUFFICIENT_DATA")
        ]
    else:
        filtered = all_invoices

    total = len(filtered)
    paged = filtered[skip : skip + limit]
    return paged, total

def create_invoice(db: Session, invoice_in: InvoiceCreate) -> Invoice:
    db_invoice = Invoice(
        invoice_number=invoice_in.invoice_number,
        vendor_name=invoice_in.vendor_name,
        invoice_date=invoice_in.invoice_date,
        customer_name=invoice_in.customer_name,
        subtotal=invoice_in.subtotal,
        tax_amount=invoice_in.tax_amount,
        total_amount=invoice_in.total_amount,
        currency=invoice_in.currency,
        source_file_path=invoice_in.source_file_path,
        pipeline_status=invoice_in.pipeline_status,
    )
    
    if invoice_in.items:
        for item_in in invoice_in.items:
            db_item = InvoiceItem(
                description=item_in.description,
                quantity=item_in.quantity,
                unit_price=item_in.unit_price,
                tax_rate=item_in.tax_rate,
                line_total=item_in.line_total
            )
            db_invoice.items.append(db_item)
            
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def update_invoice(db: Session, db_invoice: Invoice, invoice_in: InvoiceUpdate) -> Invoice:
    update_data = invoice_in.model_dump(exclude_unset=True)
    
    if "items" in update_data:
        items_data = update_data.pop("items")
        if items_data is not None:
            existing_items = {item.id: item for item in db_invoice.items}
            new_ids = {item["id"] for item in items_data if item.get("id")}
            
            # Remove deleted items
            for item_id, item_obj in existing_items.items():
                if item_id not in new_ids:
                    db.delete(item_obj)
                    
            # Add or update items
            for item_in in items_data:
                item_id = item_in.get("id")
                if item_id and item_id in existing_items:
                    db_item = existing_items[item_id]
                    for key, value in item_in.items():
                        if key != "id":
                            setattr(db_item, key, value)
                else:
                    db_item = InvoiceItem(
                        description=item_in["description"],
                        quantity=item_in.get("quantity"),
                        unit_price=item_in.get("unit_price"),
                        tax_rate=item_in.get("tax_rate"),
                        line_total=item_in.get("line_total")
                    )
                    db_invoice.items.append(db_item)
    
    # Update standard fields
    for field, value in update_data.items():
        setattr(db_invoice, field, value)
        
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def delete_invoice(db: Session, db_invoice: Invoice) -> None:
    db.delete(db_invoice)
    db.commit()
