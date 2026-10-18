import unittest
from datetime import datetime, timezone, timedelta
from app.core.database import SessionLocal
from app.models.invoice import Invoice, InvoiceItem, PipelineStatus
from app.services.historical_analysis import analyze_history, normalize_text
from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema

class TestRobustHistoricalAnalysis(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Clean up any test invoices
        self.db.query(Invoice).filter(Invoice.source_file_path == "test_robust.pdf").delete()
        self.db.commit()
        
    def tearDown(self):
        self.db.query(Invoice).filter(Invoice.source_file_path == "test_robust.pdf").delete()
        self.db.commit()
        self.db.close()
        
    def create_invoice(self, vendor, date_str, items_data, currency="USD", status=PipelineStatus.SUCCESS, invoice_number=None):
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        inv = Invoice(
            source_file_path="test_robust.pdf",
            vendor_name=vendor,
            invoice_date=dt,
            currency=currency,
            pipeline_status=status,
            invoice_number=invoice_number
        )
        self.db.add(inv)
        self.db.commit()
        self.db.refresh(inv)
        
        for i_data in items_data:
            item = InvoiceItem(
                invoice_id=inv.id,
                description=i_data["desc"],
                unit_price=i_data["price"],
                quantity=i_data.get("qty", 1)
            )
            self.db.add(item)
        self.db.commit()
        return inv

    def create_extraction_schema(self, vendor_name, invoice_date, items, currency="USD", invoice_number=None):
        return InvoiceExtractionSchema(
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            invoice_date=invoice_date,
            customer_name=None,
            subtotal=None,
            tax_amount=None,
            total_amount=None,
            currency=currency,
            items=items
        )

    def test_a_same_vendor_same_product_higher_price(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Mouse Pad", "price": 500}])
        self.create_invoice("Vendor A", "2026-02-01", [{"desc": "Mouse Pad", "price": 550}])
        
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        self.assertEqual(res["status"], "ANALYZED")
        comp = res["historical_comparisons"][0]
        self.assertEqual(comp["status"], "COMPARISON_AVAILABLE")
        self.assertEqual(comp["historical_average_unit_price"], 525.0)
        self.assertEqual(comp["latest_previous_unit_price"], 550.0)
        self.assertGreater(comp["percentage_change_from_average"], 50)
        
    def test_d_different_product_no_comparison(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Keyboard", "price": 500}])
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        comp = res["historical_comparisons"][0]
        self.assertEqual(comp["status"], "INSUFFICIENT_EVIDENCE")

    def test_e_different_vendor_same_product_no_comparison(self):
        self.create_invoice("Vendor B", "2026-01-01", [{"desc": "Mouse Pad", "price": 500}])
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")

    def test_f_quantity_changed_not_price(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Mouse Pad", "price": 500, "qty": 1}])
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=500, quantity=10, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        comp = res["historical_comparisons"][0]
        self.assertEqual(comp["percentage_change_from_average"], 0.0)

    def test_h_same_invoice_uploaded_twice(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Mouse Pad", "price": 500}], invoice_number="INV-123")
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-01-01",
            invoice_number="INV-123",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=500, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        self.assertTrue(res["is_duplicate_invoice"])
        # Same date should not be included in historical comparisons
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")

    def test_j_future_invoice_ignored(self):
        self.create_invoice("Vendor A", "2026-05-01", [{"desc": "Mouse Pad", "price": 1000}])
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")

    def test_p_product_wording_differs_slightly(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Ergonomic Mouse Pad - Black", "price": 500}])
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="ergonomic mouse pad black", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        comp = res["historical_comparisons"][0]
        self.assertEqual(comp["status"], "COMPARISON_AVAILABLE")

    def test_r_failed_historical_invoice_excluded(self):
        self.create_invoice("Vendor A", "2026-01-01", [{"desc": "Mouse Pad", "price": 500}], status=PipelineStatus.FAILED)
        extracted = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-01",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res = analyze_history(self.db, extracted, current_invoice_id=-1)
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")

    def test_24_temporal_test_with_three_invoices(self):
        self.create_invoice("Vendor A", "2026-01-10", [{"desc": "Mouse Pad", "price": 500}])
        self.create_invoice("Vendor A", "2026-02-10", [{"desc": "Mouse Pad", "price": 550}])
        self.create_invoice("Vendor A", "2026-03-10", [{"desc": "Mouse Pad", "price": 800}])
        
        # Test evaluating Mar 10
        ext_mar = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-03-10",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=800, quantity=1, tax_rate=None, line_total=None)]
        )
        res_mar = analyze_history(self.db, ext_mar, current_invoice_id=-1)
        self.assertEqual(res_mar["total_historical_invoices"], 2) # Jan + Feb
        
        # Test evaluating Jan 5
        ext_jan5 = self.create_extraction_schema(
            vendor_name="Vendor A",
            invoice_date="2026-01-05",
            items=[InvoiceItemExtractionSchema(description="Mouse Pad", unit_price=500, quantity=1, tax_rate=None, line_total=None)]
        )
        res_jan5 = analyze_history(self.db, ext_jan5, current_invoice_id=-1)
        self.assertEqual(res_jan5["status"], "INSUFFICIENT_EVIDENCE") # None

if __name__ == '__main__':
    unittest.main()
