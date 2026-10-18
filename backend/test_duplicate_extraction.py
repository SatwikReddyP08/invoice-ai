import unittest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.invoice import Invoice, PipelineStatus
from app.services.ai_extractor import InvoiceExtractionSchema

client = TestClient(app)

class TestDuplicateExtractionWorkflow(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Clean up any previous test data
        self.db.query(Invoice).filter(Invoice.invoice_number.in_(["INV-DUP-TEST", "INV-UNIQUE-123"])).delete()
        self.db.commit()

        # 1. Create the original invoice directly in DB
        self.original_invoice = Invoice(
            invoice_number="INV-DUP-TEST",
            vendor_name="Acme Corp",
            source_file_path="manual.pdf",
            pipeline_status=PipelineStatus.SUCCESS,
            total_amount=100.0
        )
        self.db.add(self.original_invoice)
        self.db.commit()
        self.db.refresh(self.original_invoice)
        
        self.test_pdf = "test_duplicate.pdf"
        with open(self.test_pdf, "wb") as f:
            f.write(b"%PDF-1.4\nDummy PDF content")

    def tearDown(self):
        self.db.query(Invoice).filter(Invoice.invoice_number.in_(["INV-DUP-TEST", "INV-UNIQUE-123"])).delete()
        # Delete any pending/failed invoices created during test
        self.db.query(Invoice).filter(Invoice.source_file_path.like("%test_duplicate.pdf")).delete()
        self.db.commit()
        self.db.close()
        
        if os.path.exists(self.test_pdf):
            os.remove(self.test_pdf)

    @patch('app.api.endpoints.invoices.extract_invoice')
    def test_duplicate_extraction_workflow(self, mock_extract):
        # 1. Normal extraction of a unique invoice (setup unique mock)
        with open(self.test_pdf, "rb") as f:
            r = client.post("/api/v1/invoices/upload", files={"file": ("test_duplicate.pdf", f, "application/pdf")})
        self.assertEqual(r.status_code, 201)
        unique_id = r.json()["invoice_id"]
        
        mock_extract.return_value = InvoiceExtractionSchema(
            invoice_number="INV-UNIQUE-123",
            vendor_name="Unique Corp",
            invoice_date=None,
            customer_name=None,
            subtotal=None,
            tax_amount=None,
            currency=None,
            total_amount=50.0,
            items=[]
        )
        r = client.post(f"/api/v1/invoices/{unique_id}/extract")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pipeline_status"], "SUCCESS")
        
        # 2. Upload a new document for duplicate test
        with open(self.test_pdf, "rb") as f:
            r = client.post("/api/v1/invoices/upload", files={"file": ("test_duplicate.pdf", f, "application/pdf")})
        self.assertEqual(r.status_code, 201)
        duplicate_id = r.json()["invoice_id"]
        
        # Force the AI extractor to return the exact same vendor and invoice number as the original
        mock_extract.return_value = InvoiceExtractionSchema(
            invoice_number="INV-DUP-TEST",
            vendor_name="Acme Corp",
            invoice_date=None,
            customer_name=None,
            subtotal=None,
            tax_amount=None,
            currency=None,
            total_amount=999.0,
            items=[]
        )
        
        # 3. Extract and expect a 200 Success since duplicate constraint is removed
        r = client.post(f"/api/v1/invoices/{duplicate_id}/extract")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pipeline_status"], "SUCCESS")
        
        # 4. Correct database status after successful extraction
        duplicate_invoice = self.db.query(Invoice).filter(Invoice.id == duplicate_id).first()
        self.assertEqual(duplicate_invoice.pipeline_status, PipelineStatus.SUCCESS)
        self.assertEqual(duplicate_invoice.vendor_name, "Acme Corp")
        
        # 5. Existing original invoice remains unchanged
        original = self.db.query(Invoice).filter(Invoice.id == self.original_invoice.id).first()
        self.assertEqual(original.total_amount, 100.0) # Still 100, not 999
        self.assertEqual(original.pipeline_status, PipelineStatus.SUCCESS)

if __name__ == "__main__":
    unittest.main()
