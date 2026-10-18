import os
import base64
import filetype
import fitz  # PyMuPDF
from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field
import groq
from app.core.config import settings
import logging

class InvoiceItemExtractionSchema(BaseModel):
    description: str = Field(description="Description of the line item")
    quantity: Optional[float] = Field(description="Quantity of the item")
    unit_price: Optional[float] = Field(description="Unit price of the item")
    tax_rate: Optional[float] = Field(description="Tax rate applied to this item as a decimal (e.g., 0.08 for 8%)")
    line_total: Optional[float] = Field(description="Total amount for this line item")
    model_config = {"extra": "forbid"}

class InvoiceExtractionSchema(BaseModel):
    invoice_number: Optional[str] = Field(description="Invoice number")
    vendor_name: Optional[str] = Field(description="Name of the vendor/supplier")
    invoice_date: Optional[date] = Field(description="Date of the invoice")
    customer_name: Optional[str] = Field(description="Name of the customer/buyer")
    subtotal: Optional[float] = Field(description="Subtotal amount before taxes")
    tax_amount: Optional[float] = Field(description="Total tax amount")
    total_amount: Optional[float] = Field(description="Grand total amount including taxes")
    currency: Optional[str] = Field(description="3-letter currency code (e.g., USD, EUR)")
    items: List[InvoiceItemExtractionSchema] = Field(description="List of items on the invoice")
    model_config = {"extra": "forbid"}

def _process_document_to_base64_images(file_path: str) -> List[str]:
    """
    Converts a document (PDF or Image) into a list of base64 encoded JPEG strings.
    For PDFs, it rasterizes up to the first 3 pages.
    """
    kind = filetype.guess(file_path)
    if not kind:
        raise ValueError(f"Could not determine file type for {file_path}")
        
    mime_type = kind.mime
    base64_images = []
    
    if mime_type == "application/pdf":
        try:
            doc = fitz.open(file_path)
            # Limit to first 3 pages to avoid excessive token usage
            page_count = min(len(doc), 3)
            for i in range(page_count):
                page = doc.load_page(i)
                # Render to pixmap with a reasonable resolution (e.g., 150 DPI)
                # Matrix(2, 2) scales by 2x which is roughly 144 DPI
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("jpeg")
                base64_images.append(base64.b64encode(img_data).decode('utf-8'))
            doc.close()
        except Exception as e:
            raise ValueError(f"Failed to process PDF: {e}")
    elif mime_type.startswith("image/"):
        try:
            with open(file_path, "rb") as f:
                base64_images.append(base64.b64encode(f.read()).decode('utf-8'))
        except Exception as e:
            raise ValueError(f"Failed to process image: {e}")
    else:
        raise ValueError(f"Unsupported mime type for extraction: {mime_type}")
        
    return base64_images

def extract_invoice(file_path: str) -> InvoiceExtractionSchema:
    """
    Extract structured data from an invoice document using Groq vision models.
    """
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Invoice file not found: {file_path}")

    client = groq.Groq(api_key=settings.GROQ_API_KEY)
    
    # Process document into base64 images
    base64_images = _process_document_to_base64_images(file_path)
    if not base64_images:
        raise ValueError("No images could be extracted from the document")

    # Build the prompt
    prompt = (
        "Extract the following fields from the attached invoice document. "
        "Extract only information actually present in the document. "
        "Do not invent missing values. Use null when a value cannot be determined. "
        "Preserve the document's numeric values accurately. "
        "Distinguish subtotal, tax, and grand total. "
        "Extract every visible line item. "
        "Return the invoice currency when identifiable as a 3-letter code."
    )

    # Construct messages with text and all image URLs
    content_array = [{"type": "text", "text": prompt}]
    for img_b64 in base64_images:
        content_array.append({
            "type": "image_url", 
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
        })

    # Call the Groq API enforcing structured output via json_schema
    try:
        response = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "user", "content": content_array}
            ],
            response_format={
                "type": "json_schema", 
                "json_schema": {
                    "name": "invoice_extraction", 
                    "schema": InvoiceExtractionSchema.model_json_schema(), 
                    "strict": True
                }
            },
            temperature=0.0
        )

        # Parse and return the structured data
        message_content = response.choices[0].message.content
        return InvoiceExtractionSchema.model_validate_json(message_content)
    except Exception as e:
        logging.error(f"Groq API extraction failed: {e}")
        raise
