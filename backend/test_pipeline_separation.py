import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.invoice import Invoice, PipelineStatus
from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema
from app.services.ai_review import InvoiceReviewSchema

client = TestClient(app)

class TestPipelineSeparation(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.test_pdf = "test_pipeline.pdf"
        with open(self.test_pdf, "wb") as f:
            f.write(b"%PDF-1.4\nDummy PDF content")

    def tearDown(self):
        self.db.query(Invoice).filter(Invoice.source_file_path.like("%test_pipeline.pdf")).delete()
        self.db.commit()
        self.db.close()
        import os
        if os.path.exists(self.test_pdf):
            os.remove(self.test_pdf)

    @patch('app.api.endpoints.invoices.extract_invoice')
    @patch('app.api.endpoints.invoices.analyze_financials')
    @patch('app.api.endpoints.invoices.analyze_history')
    @patch('app.api.endpoints.invoices.review_invoice_with_llm')
    def test_pipeline_execution_order(self, mock_review, mock_history, mock_financials, mock_extract):
        # Setup mocks
        mock_extract.return_value = InvoiceExtractionSchema(
            invoice_number="PIPE-123",
            vendor_name="Pipeline Corp",
            invoice_date="2026-09-29",
            customer_name=None,
            subtotal=100.0,
            tax_amount=10.0,
            currency="USD",
            total_amount=110.0,
            items=[
                InvoiceItemExtractionSchema(description="Item 1", quantity=1.0, unit_price=100.0, tax_rate=None, line_total=100.0)
            ]
        )
        mock_financials.return_value = {"total_consistent": True}
        mock_history.return_value = {"has_history": False}
        mock_review.return_value = {"review_status": "APPROVED", "key_findings": [], "explanation": "Test"}

        # 1. Upload
        with open(self.test_pdf, "rb") as f:
            r = client.post("/api/v1/invoices/upload", files={"file": ("test_pipeline.pdf", f, "application/pdf")})
        self.assertEqual(r.status_code, 201)
        invoice_id = r.json()["invoice_id"]
        
        # 2. Extract / Process
        r = client.post(f"/api/v1/invoices/{invoice_id}/extract")
        self.assertEqual(r.status_code, 200)
        
        # 3. Assert calls happened
        mock_extract.assert_called_once()
        mock_financials.assert_called_once()
        mock_history.assert_called_once()
        mock_review.assert_called_once()
        
        # Verify evidence passed to review includes financial analysis and history
        evidence = mock_review.call_args[0][0]
        self.assertIn("financial_validation", evidence)
        self.assertIn("historical_context", evidence)
        self.assertEqual(evidence["financial_validation"]["total_consistent"], True)

    @patch('app.api.endpoints.invoices.extract_invoice')
    @patch('app.api.endpoints.invoices.review_invoice_with_llm')
    def test_pipeline_failure_isolation(self, mock_review, mock_extract):
        mock_extract.return_value = InvoiceExtractionSchema(
            invoice_number="PIPE-FAIL",
            vendor_name="Pipeline Corp",
            invoice_date=None,
            customer_name=None,
            subtotal=100.0,
            tax_amount=10.0,
            currency="USD",
            total_amount=110.0,
            items=[]
        )
        
        # Fail the review stage
        mock_review.side_effect = Exception("LLM Review Failed")

        with open(self.test_pdf, "rb") as f:
            r = client.post("/api/v1/invoices/upload", files={"file": ("test_pipeline.pdf", f, "application/pdf")})
        invoice_id = r.json()["invoice_id"]
        
        r = client.post(f"/api/v1/invoices/{invoice_id}/extract")
        self.assertEqual(r.status_code, 500)
        
        # Check DB to ensure extraction data is persisted!
        inv = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        self.assertEqual(inv.pipeline_status, PipelineStatus.FAILED)
        self.assertEqual(inv.vendor_name, "Pipeline Corp")
        self.assertEqual(inv.total_amount, 110.0)

if __name__ == "__main__":
    unittest.main()
