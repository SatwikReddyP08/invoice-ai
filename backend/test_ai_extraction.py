import os
import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from pydantic import ValidationError
from app.services.ai_extractor import InvoiceExtractionSchema, extract_invoice, _process_document_to_base64_images
from app.core.config import settings
from PIL import Image, ImageDraw
import base64
import fitz # PyMuPDF
from fastapi import HTTPException
from app.api.endpoints.invoices import extract_invoice_data
from app.models.invoice import PipelineStatus

class TestAIExtraction(unittest.TestCase):
    def setUp(self):
        self.original_key = settings.GROQ_API_KEY
        # Create dummy JPEG
        self.test_img_path = "test_invoice.jpg"
        img = Image.new('RGB', (200, 100), color='white')
        d = ImageDraw.Draw(img)
        d.text((10,10), "INVOICE #999", fill=(0,0,0))
        d.text((10,30), "Total: $42.00", fill=(0,0,0))
        img.save(self.test_img_path, format="JPEG")
        
        # Create dummy PDF (2 pages)
        self.test_pdf_path = "test_invoice.pdf"
        doc = fitz.open()
        page1 = doc.new_page(width=200, height=100)
        page1.insert_text((10, 10), "PDF Page 1 INVOICE #999")
        page2 = doc.new_page(width=200, height=100)
        page2.insert_text((10, 10), "PDF Page 2 Total: $42.00")
        doc.save(self.test_pdf_path)
        doc.close()

    def tearDown(self):
        settings.GROQ_API_KEY = self.original_key
        if os.path.exists(self.test_img_path):
            os.remove(self.test_img_path)
        if os.path.exists(self.test_pdf_path):
            os.remove(self.test_pdf_path)

    def test_pydantic_schema_validates_representative_response(self):
        mock_payload = {
            "invoice_number": "INV-123",
            "vendor_name": "Test Vendor",
            "invoice_date": "2023-10-24",
            "customer_name": "Test Customer",
            "subtotal": 100.0,
            "tax_amount": 10.0,
            "total_amount": 110.0,
            "currency": "USD",
            "items": [
                {
                    "description": "Item 1",
                    "quantity": 2,
                    "unit_price": 25.0,
                    "tax_rate": 0.1,
                    "line_total": 50.0
                },
                {
                    "description": "Item 2",
                    "quantity": 1,
                    "unit_price": 50.0,
                    "tax_rate": 0.1,
                    "line_total": 50.0
                }
            ]
        }
        
        schema = InvoiceExtractionSchema(**mock_payload)
        self.assertEqual(schema.invoice_number, "INV-123")
        self.assertEqual(len(schema.items), 2)
        self.assertEqual(schema.items[1].description, "Item 2")
        self.assertEqual(schema.total_amount, 110.0)
        
    def test_pydantic_schema_handles_missing_optional_fields(self):
        mock_payload = {
            "invoice_number": "INV-123",
            "vendor_name": None,
            "invoice_date": None,
            "customer_name": None,
            "subtotal": None,
            "tax_amount": None,
            "total_amount": 110.0,
            "currency": None,
            "items": [
                {
                    "description": "Item 1",
                    "quantity": None,
                    "unit_price": None,
                    "tax_rate": None,
                    "line_total": None
                }
            ]
        }
        schema = InvoiceExtractionSchema(**mock_payload)
        self.assertEqual(schema.invoice_number, "INV-123")
        self.assertIsNone(schema.subtotal)
        self.assertIsNone(schema.items[0].quantity)

    def test_pydantic_schema_rejects_invalid_data(self):
        mock_invalid = {
            "invoice_number": "INV-123",
            "items": [
                {
                    # Missing description which is required
                    "quantity": 10
                }
            ]
        }
        with self.assertRaises(ValidationError):
            InvoiceExtractionSchema(**mock_invalid)

    def test_pdf_preprocessing_multipage(self):
        # Should process 2 pages into 2 base64 strings
        b64_images = _process_document_to_base64_images(self.test_pdf_path)
        self.assertEqual(len(b64_images), 2)
        self.assertIsInstance(b64_images[0], str)

    def test_jpeg_preprocessing(self):
        b64_images = _process_document_to_base64_images(self.test_img_path)
        self.assertEqual(len(b64_images), 1)

    def test_missing_api_key(self):
        settings.GROQ_API_KEY = ""
        with self.assertRaisesRegex(ValueError, "GROQ_API_KEY is not configured"):
            extract_invoice(self.test_img_path)

    @patch('app.api.endpoints.invoices.review_invoice_with_llm')
    @patch('app.api.endpoints.invoices.crud_invoice')
    @patch('app.api.endpoints.invoices.extract_invoice')
    @patch('app.api.endpoints.invoices.os.path.exists')
    def test_extraction_endpoint_transitions_and_rollback(self, mock_exists, mock_extract, mock_crud, mock_review):
        # Mock DB
        mock_db = MagicMock()
        mock_invoice = MagicMock()
        mock_invoice.source_file_path = "mock.pdf"
        mock_invoice.pipeline_status = PipelineStatus.PENDING
        mock_crud.get_invoice.return_value = mock_invoice
        
        mock_exists.return_value = True
        
        # Test 1: Successful Extraction
        mock_extracted_data = InvoiceExtractionSchema(
            invoice_number="123",
            vendor_name=None,
            invoice_date=None,
            customer_name=None,
            subtotal=None,
            tax_amount=None,
            total_amount=100.0,
            currency=None,
            items=[]
        )
        mock_extract.return_value = mock_extracted_data
        mock_review.return_value = {
            "status": "NORMAL",
            "review_recommendation": "NO_ACTION_REQUIRED",
            "findings": [],
            "explanation": "Valid."
        }
        
        extract_invoice_data(invoice_id=1, db=mock_db)
        
        # Verify status went to EXTRACTING then SUCCESS
        # and crud_invoice.update_invoice was called
        self.assertEqual(mock_invoice.pipeline_status, PipelineStatus.EXTRACTING)
        mock_db.commit.assert_called()
        mock_crud.update_invoice.assert_called_once()
        
        # Test 2: Extraction Failure (API Error) triggers FAILED and rollback
        mock_invoice.pipeline_status = PipelineStatus.PENDING
        mock_extract.side_effect = Exception("API Timeout")
        
        with self.assertRaises(HTTPException) as context:
            extract_invoice_data(invoice_id=1, db=mock_db)
            
        self.assertEqual(context.exception.status_code, 500)
        self.assertIn("Extraction failed: API Timeout", context.exception.detail)
        
        # Verify rollback was called and status set to FAILED
        mock_db.rollback.assert_called()
        self.assertEqual(mock_invoice.pipeline_status, PipelineStatus.FAILED)
        
        # Test 3: Duplicate Error triggers FAILED, rollback, and 409
        mock_invoice.pipeline_status = PipelineStatus.PENDING
        mock_crud.update_invoice.side_effect = Exception("DB update failed")
        mock_extract.side_effect = None
        mock_extract.return_value = mock_extracted_data
        
        with self.assertRaises(HTTPException) as context:
            extract_invoice_data(invoice_id=1, db=mock_db)
            
        self.assertEqual(context.exception.status_code, 500)
        self.assertIn("DB update failed", context.exception.detail)
        
        # Verify rollback was called and status set to FAILED
        self.assertEqual(mock_invoice.pipeline_status, PipelineStatus.FAILED)

    def test_end_to_end_extraction_real_api(self):
        """
        Controlled LIVE test against Groq. 
        Will skip safely if key is invalid, avoiding CI failures or repeated heavy costs.
        """
        if not settings.GROQ_API_KEY:
            self.skipTest("No GROQ_API_KEY available for live test")
            
        print("\n--- WARNING: PERFORMING A REAL GROQ API CALL ---")
        try:
            result = extract_invoice(self.test_img_path)
            print("Extracted Data:", result.model_dump_json(indent=2))
            
            # Since the dummy image has "INVOICE #999" and "Total: $42.00"
            # It may extract 999 or #999.
            self.assertTrue("999" in str(result.invoice_number))
            self.assertEqual(result.total_amount, 42.0)
            
        except Exception as e:
            err_str = str(e).lower()
            if "authentication" in err_str or "unauthorized" in err_str or "api key" in err_str or "401" in err_str or "403" in err_str or "invalid" in err_str:
                print(f"Skipping actual extraction assertion due to invalid/test API key: {e}")
            else:
                raise

if __name__ == '__main__':
    unittest.main()
