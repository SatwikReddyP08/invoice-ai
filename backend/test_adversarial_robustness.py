import unittest
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.core.database import SessionLocal
from app.models.invoice import Invoice, InvoiceItem, PipelineStatus
from app.services.financial_analysis import analyze_financials
from app.services.historical_analysis import analyze_history, normalize_vendor_name, normalize_product_name
from app.services.ai_review import post_validate_review, InvoiceReviewSchema, FindingSchema
from app.services.ai_extractor import InvoiceExtractionSchema, InvoiceItemExtractionSchema
from app.api.endpoints.invoices import extract_invoice_data
from app.core.config import settings

class TestAdversarialRobustness(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        # Clean up any test invoices
        self.db.query(Invoice).filter(Invoice.source_file_path.like("test_adv_%")).delete()
        self.db.commit()

    def tearDown(self):
        self.db.query(Invoice).filter(Invoice.source_file_path.like("test_adv_%")).delete()
        self.db.commit()
        self.db.close()

    def create_db_invoice(
        self,
        vendor: str,
        date_str: str,
        items_data: list,
        currency: str = "USD",
        status: PipelineStatus = PipelineStatus.SUCCESS,
        invoice_number: str = None,
        source_tag: str = "test_adv_default.pdf"
    ) -> Invoice:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        subtotal = sum(i["price"] * i.get("qty", 1) for i in items_data)
        tax = round(subtotal * 0.1, 2)
        total = subtotal + tax

        inv = Invoice(
            source_file_path=source_tag,
            vendor_name=vendor,
            invoice_date=dt,
            currency=currency,
            pipeline_status=status,
            invoice_number=invoice_number,
            subtotal=Decimal(str(subtotal)),
            tax_amount=Decimal(str(tax)),
            total_amount=Decimal(str(total)),
            extraction_completed_at=datetime.now(timezone.utc) if status == PipelineStatus.SUCCESS else None
        )
        self.db.add(inv)
        self.db.commit()
        self.db.refresh(inv)

        for i_data in items_data:
            qty = i_data.get("qty", 1)
            price = i_data["price"]
            item = InvoiceItem(
                invoice_id=inv.id,
                description=i_data["desc"],
                unit_price=Decimal(str(price)),
                quantity=Decimal(str(qty)),
                line_total=Decimal(str(round(qty * price, 2)))
            )
            self.db.add(item)
        self.db.commit()
        self.db.refresh(inv)
        return inv

    def make_schema(self, vendor, inv_date, items, currency="USD", invoice_number="INV-TEST", subtotal=None, tax=None, total=None):
        item_schemas = [
            InvoiceItemExtractionSchema(
                description=it["desc"],
                quantity=it.get("qty", 1.0),
                unit_price=it.get("price"),
                tax_rate=it.get("tax_rate", 0.1),
                line_total=it.get("line_total", round(it.get("qty", 1.0) * (it.get("price") or 0.0), 2))
            ) for it in items
        ]
        calc_sub = sum(it.line_total or 0.0 for it in item_schemas)
        calc_tax = round(calc_sub * 0.1, 2)
        calc_tot = calc_sub + calc_tax

        return InvoiceExtractionSchema(
            invoice_number=invoice_number,
            vendor_name=vendor,
            invoice_date=datetime.strptime(inv_date, "%Y-%m-%d").date() if isinstance(inv_date, str) else inv_date,
            customer_name="Test Customer Ltd",
            subtotal=subtotal if subtotal is not None else calc_sub,
            tax_amount=tax if tax is not None else calc_tax,
            total_amount=total if total is not None else calc_tot,
            currency=currency,
            items=item_schemas
        )

    # --------------------------------------------------------------------------
    # Scenario 1: Higher, lower, and unchanged unit prices
    # --------------------------------------------------------------------------
    def test_01_unit_price_variations(self):
        self.create_db_invoice("Acme Supplies", "2026-01-01", [{"desc": "Standard Stapler", "price": 100.0}])

        # Higher (+60%)
        schema_high = self.make_schema("Acme Supplies", "2026-02-01", [{"desc": "Standard Stapler", "price": 160.0}])
        res_high = analyze_history(self.db, schema_high, current_invoice_id=-1)
        comp_h = res_high["historical_comparisons"][0]
        self.assertEqual(comp_h["change_category"], "MATERIAL_INCREASE")
        self.assertTrue(comp_h["threshold_exceeded"])
        self.assertEqual(comp_h["percentage_change_from_previous"], 60.0)

        # Lower (-25%)
        schema_low = self.make_schema("Acme Supplies", "2026-02-01", [{"desc": "Standard Stapler", "price": 75.0}])
        res_low = analyze_history(self.db, schema_low, current_invoice_id=-1)
        comp_l = res_low["historical_comparisons"][0]
        self.assertEqual(comp_l["change_category"], "MATERIAL_DECREASE")
        self.assertTrue(comp_l["threshold_exceeded"])
        self.assertEqual(comp_l["percentage_change_from_previous"], -25.0)

        # Unchanged (0%)
        schema_same = self.make_schema("Acme Supplies", "2026-02-01", [{"desc": "Standard Stapler", "price": 100.0}])
        res_same = analyze_history(self.db, schema_same, current_invoice_id=-1)
        comp_s = res_same["historical_comparisons"][0]
        self.assertEqual(comp_s["change_category"], "UNCHANGED")
        self.assertFalse(comp_s["threshold_exceeded"])
        self.assertEqual(comp_s["percentage_change_from_previous"], 0.0)

    # --------------------------------------------------------------------------
    # Scenario 2: Exactly-at-threshold and boundary changes
    # --------------------------------------------------------------------------
    def test_02_threshold_boundary_behavior(self):
        self.create_db_invoice("Boundary Tech", "2026-01-01", [{"desc": "USB Drive 64GB", "price": 100.0}])

        # Exactly at threshold (+10.0%)
        schema_10 = self.make_schema("Boundary Tech", "2026-02-01", [{"desc": "USB Drive 64GB", "price": 110.0}])
        res_10 = analyze_history(self.db, schema_10, current_invoice_id=-1)
        comp_10 = res_10["historical_comparisons"][0]
        self.assertEqual(comp_10["percentage_change_from_previous"], 10.0)
        self.assertTrue(comp_10["threshold_exceeded"])
        self.assertEqual(comp_10["change_category"], "SIGNIFICANT_INCREASE")

        # Just below threshold (+9.9%)
        schema_99 = self.make_schema("Boundary Tech", "2026-02-01", [{"desc": "USB Drive 64GB", "price": 109.9}])
        res_99 = analyze_history(self.db, schema_99, current_invoice_id=-1)
        comp_99 = res_99["historical_comparisons"][0]
        self.assertEqual(comp_99["percentage_change_from_previous"], 9.9)
        self.assertFalse(comp_99["threshold_exceeded"])
        self.assertEqual(comp_99["change_category"], "MINOR_INCREASE")

        # Just above threshold (+10.1%)
        schema_101 = self.make_schema("Boundary Tech", "2026-02-01", [{"desc": "USB Drive 64GB", "price": 110.1}])
        res_101 = analyze_history(self.db, schema_101, current_invoice_id=-1)
        comp_101 = res_101["historical_comparisons"][0]
        self.assertTrue(comp_101["threshold_exceeded"])
        self.assertEqual(comp_101["change_category"], "SIGNIFICANT_INCREASE")

    # --------------------------------------------------------------------------
    # Scenario 3: Different vendors and different products
    # --------------------------------------------------------------------------
    def test_03_conservative_vendor_and_product_matching(self):
        self.create_db_invoice("Alpha Office Solutions Pvt Ltd", "2026-01-01", [{"desc": "Desk Organizer", "price": 25.0}])

        # Different Vendor: "Alpha Technologies Pvt Ltd" (shared word 'Alpha', but distinct core entity)
        schema_diff_v = self.make_schema("Alpha Technologies Pvt Ltd", "2026-02-01", [{"desc": "Desk Organizer", "price": 50.0}])
        res_v = analyze_history(self.db, schema_diff_v, current_invoice_id=-1)
        self.assertEqual(res_v["status"], "INSUFFICIENT_EVIDENCE")

        # Same Vendor, completely different product ("Monitor Arm" vs "Desk Organizer")
        schema_diff_p = self.make_schema("Alpha Office Solutions Pvt Ltd", "2026-02-01", [{"desc": "Monitor Arm", "price": 75.0}])
        res_p = analyze_history(self.db, schema_diff_p, current_invoice_id=-1)
        self.assertEqual(res_p["historical_comparisons"][0]["status"], "INSUFFICIENT_EVIDENCE")

    # --------------------------------------------------------------------------
    # Scenario 4: Quantity-only and tax-only changes
    # --------------------------------------------------------------------------
    def test_04_quantity_and_tax_separation(self):
        self.create_db_invoice("Bulk Vendor Inc", "2026-01-01", [{"desc": "Paper Reams", "price": 5.0, "qty": 10}])

        # Quantity change: ordered 500 reams instead of 10, unit price unchanged at 5.0
        schema_qty = self.make_schema("Bulk Vendor Inc", "2026-02-01", [{"desc": "Paper Reams", "price": 5.0, "qty": 500}])
        res_qty = analyze_history(self.db, schema_qty, current_invoice_id=-1)
        comp_q = res_qty["historical_comparisons"][0]
        self.assertEqual(comp_q["percentage_change_from_previous"], 0.0)
        self.assertEqual(comp_q["change_category"], "UNCHANGED")
        self.assertFalse(comp_q["threshold_exceeded"])

        # Tax-only change: subtotal is 50.0, tax increased from 10% (5.0) to 20% (10.0)
        schema_tax = self.make_schema("Bulk Vendor Inc", "2026-02-01", [{"desc": "Paper Reams", "price": 5.0, "qty": 10}], tax=10.0, total=60.0)
        fin_tax = analyze_financials(schema_tax)
        self.assertTrue(fin_tax["total_consistent"])
        self.assertEqual(fin_tax["tax_amount"], 10.0)

    # --------------------------------------------------------------------------
    # Scenario 5: Discounts and invoice-level discounts
    # --------------------------------------------------------------------------
    def test_05_discounts_detection(self):
        # Invoice has subtotal 1000.0, tax 100.0, but total is 950.0 (implied 150 discount)
        schema_disc = self.make_schema("Discount Mart", "2026-02-01", [{"desc": "Workstation", "price": 1000.0, "qty": 1}], subtotal=1000.0, tax=100.0, total=950.0)
        fin_disc = analyze_financials(schema_disc)
        self.assertFalse(fin_disc["total_consistent"])
        self.assertEqual(fin_disc["discount_detected"], 150.0)
        self.assertTrue(any("discount" in a.lower() for a in fin_disc["anomalies"]))

    # --------------------------------------------------------------------------
    # Scenario 6: Currency mismatches handled safely
    # --------------------------------------------------------------------------
    def test_06_currency_mismatch_protection(self):
        # Historical invoice in EUR
        self.create_db_invoice("Global Logistics", "2026-01-01", [{"desc": "Shipping Container", "price": 500.0}], currency="EUR")

        # Current invoice in USD (500.0 USD should NOT be matched against 500.0 EUR)
        schema_usd = self.make_schema("Global Logistics", "2026-02-01", [{"desc": "Shipping Container", "price": 500.0}], currency="USD")
        res_mismatch = analyze_history(self.db, schema_usd, current_invoice_id=-1)
        self.assertEqual(res_mismatch["status"], "INSUFFICIENT_EVIDENCE")
        self.assertGreaterEqual(res_mismatch["currency_mismatches_excluded"], 1)

    # --------------------------------------------------------------------------
    # Scenario 7: Zero, negative, missing, and malformed monetary fields
    # --------------------------------------------------------------------------
    def test_07_invalid_monetary_arithmetic(self):
        # Create prior invoice for Anomaly Co to allow comparison
        self.create_db_invoice("Anomaly Co", "2026-01-01", [{"desc": "Defective Widget", "price": 50.0}], currency="USD")

        # Negative unit price, zero quantity, invalid currency, negative total
        schema_invalid = self.make_schema(
            "Anomaly Co", "2026-02-01",
            [
                {"desc": "Defective Widget", "price": -50.0, "qty": 0.0, "line_total": 0.0},
                {"desc": "Valid Widget", "price": 100.0, "qty": 1.0, "line_total": 100.0}
            ],
            currency="INVALID_CURRENCY",
            total=-25.0
        )
        fin_inv = analyze_financials(schema_invalid)
        self.assertEqual(fin_inv["status"], "INVALID_DATA")
        self.assertFalse(fin_inv["currency_valid"])
        self.assertTrue(fin_inv["has_invalid_quantities"])
        self.assertTrue(fin_inv["has_invalid_unit_prices"])
        self.assertTrue(fin_inv["has_negative_amounts"])

        # Historical analysis safe from non-positive current prices
        schema_hist_invalid = self.make_schema(
            "Anomaly Co", "2026-02-01",
            [
                {"desc": "Defective Widget", "price": -50.0, "qty": 1.0, "line_total": -50.0},
                {"desc": "Valid Widget", "price": 100.0, "qty": 1.0, "line_total": 100.0}
            ],
            currency="USD"
        )
        res_inv = analyze_history(self.db, schema_hist_invalid, current_invoice_id=-1)
        comp_defective = [c for c in res_inv["historical_comparisons"] if c["product"] == "Defective Widget"][0]
        self.assertEqual(comp_defective["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("Non-positive", comp_defective["message"])

    # --------------------------------------------------------------------------
    # Scenario 8: Duplicate invoice uploads excluded from history
    # --------------------------------------------------------------------------
    def test_08_duplicate_invoice_exclusion(self):
        # Initial invoice uploaded
        self.create_db_invoice("Acme Duplicates", "2026-01-15", [{"desc": "Ink Cartridge", "price": 40.0}], invoice_number="INV-DUP-1")

        # Duplicate submission with same vendor and same invoice number
        schema_dup = self.make_schema("Acme Duplicates", "2026-01-15", [{"desc": "Ink Cartridge", "price": 40.0}], invoice_number="INV-DUP-1")
        res_dup = analyze_history(self.db, schema_dup, current_invoice_id=-1)
        self.assertTrue(res_dup["is_duplicate_invoice"])
        self.assertEqual(res_dup["duplicate_invoices_excluded"], 1)
        # Duplicate excluded from historical price baseline
        self.assertEqual(res_dup["status"], "INSUFFICIENT_EVIDENCE")

    # --------------------------------------------------------------------------
    # Scenario 9: Future-dated invoices and reordered upload sequences
    # --------------------------------------------------------------------------
    def test_09_future_dated_invoices_strict_ordering(self):
        # Inverted upload order: Future invoice (Dec 2026) is uploaded FIRST
        self.create_db_invoice("Temporal Dynamics", "2026-12-01", [{"desc": "Quantum Processor", "price": 5000.0}])

        # Current invoice being evaluated is from earlier in the year (March 2026)
        schema_past = self.make_schema("Temporal Dynamics", "2026-03-01", [{"desc": "Quantum Processor", "price": 3000.0}])
        res_past = analyze_history(self.db, schema_past, current_invoice_id=-1)

        # Future invoice (Dec 2026) must NOT leak into March 2026 evaluation!
        self.assertEqual(res_past["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res_past["future_invoices_excluded"], 1)

    # --------------------------------------------------------------------------
    # Scenario 10: Same-date invoices policy
    # --------------------------------------------------------------------------
    def test_10_same_date_invoice_policy(self):
        # Invoice on 2026-05-15
        self.create_db_invoice("SameDay Corp", "2026-05-15", [{"desc": "Courier Service", "price": 100.0}], invoice_number="INV-SD-A")

        # Second invoice on exact same date 2026-05-15
        schema_same_date = self.make_schema("SameDay Corp", "2026-05-15", [{"desc": "Courier Service", "price": 120.0}], invoice_number="INV-SD-B")
        res_sd = analyze_history(self.db, schema_same_date, current_invoice_id=-1)

        # Same date invoices are excluded to prevent temporal ambiguity
        self.assertEqual(res_sd["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res_sd["same_date_invoices_excluded"], 1)

    # --------------------------------------------------------------------------
    # Scenario 11: Failed or incomplete historical records excluded
    # --------------------------------------------------------------------------
    def test_11_failed_records_excluded(self):
        # Create FAILED and PENDING invoices
        self.create_db_invoice("Retry Corp", "2026-01-01", [{"desc": "Server Rack", "price": 1000.0}], status=PipelineStatus.FAILED)
        self.create_db_invoice("Retry Corp", "2026-02-01", [{"desc": "Server Rack", "price": 1000.0}], status=PipelineStatus.PENDING)

        schema_now = self.make_schema("Retry Corp", "2026-03-01", [{"desc": "Server Rack", "price": 1200.0}])
        res = analyze_history(self.db, schema_now, current_invoice_id=-1)
        self.assertEqual(res["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res["total_historical_invoices"], 0)

    # --------------------------------------------------------------------------
    # Scenario 12: Outlier-contaminated price history
    # --------------------------------------------------------------------------
    def test_12_outlier_detection_and_sample_size(self):
        # 3 normal invoices, 1 gross typo outlier (6000 instead of ~600)
        self.create_db_invoice("Office Outliers", "2026-01-01", [{"desc": "Ergonomic Chair", "price": 600.0}])
        self.create_db_invoice("Office Outliers", "2026-02-01", [{"desc": "Ergonomic Chair", "price": 620.0}])
        self.create_db_invoice("Office Outliers", "2026-03-01", [{"desc": "Ergonomic Chair", "price": 610.0}])
        self.create_db_invoice("Office Outliers", "2026-04-01", [{"desc": "Ergonomic Chair", "price": 6000.0}]) # 10x typo outlier

        schema_out = self.make_schema("Office Outliers", "2026-05-01", [{"desc": "Ergonomic Chair", "price": 630.0}])
        res_out = analyze_history(self.db, schema_out, current_invoice_id=-1)

        comp = res_out["historical_comparisons"][0]
        self.assertEqual(comp["sample_size"], 4)
        self.assertIn(6000.0, comp["outliers_detected"])
        self.assertEqual(comp["historical_median_unit_price"], 615.0)

    # --------------------------------------------------------------------------
    # Scenario 13: Insufficient historical evidence explicit representation
    # --------------------------------------------------------------------------
    def test_13_insufficient_evidence_representation(self):
        # New vendor never seen before
        schema_new = self.make_schema("Brand New Vendor", "2026-05-01", [{"desc": "New Gadget", "price": 200.0}])
        res_hist = analyze_history(self.db, schema_new, current_invoice_id=-1)
        self.assertEqual(res_hist["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res_hist["total_historical_invoices"], 0)

        # Stage 3 post-validator test: prevents hallucinating price comparisons when evidence is insufficient
        fake_llm_review = InvoiceReviewSchema(
            status="REVIEW_RECOMMENDED",
            review_recommendation="REVIEW_RECOMMENDED",
            findings=[
                FindingSchema(
                    type="PRICE_CHANGE",
                    severity="HIGH",
                    product="New Gadget",
                    evidence="Price increased by 50% from prior purchase.",
                    explanation="Vendor is overcharging."
                )
            ],
            explanation="Flagging price increase anomaly."
        )
        evidence = {
            "historical_context": res_hist,
            "financial_validation": {"status": "VALID", "total_consistent": True}
        }
        validated = post_validate_review(fake_llm_review, evidence)
        self.assertEqual(validated.status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(validated.review_recommendation, "INSUFFICIENT_DATA")
        self.assertEqual(validated.findings[0].type, "INSUFFICIENT_EVIDENCE")

    # --------------------------------------------------------------------------
    # Scenario 14: Stage 3 hallucination, anti-fraud enforcement, and retry behavior
    # --------------------------------------------------------------------------
    def test_14_stage3_guardrails_and_retry_flow(self):
        # 1. Anti-fraud enforcement: Banned terms ('fraud', 'scam') sanitized
        accusatory_review = InvoiceReviewSchema(
            status="REVIEW_RECOMMENDED",
            review_recommendation="REVIEW_RECOMMENDED",
            findings=[
                FindingSchema(
                    type="PRICE_CHANGE",
                    severity="HIGH",
                    product="Mouse Pad",
                    evidence="Vendor raised price significantly.",
                    explanation="This is a fraudulent invoice and a scam."
                )
            ],
            explanation="Detected clear fraud by the vendor."
        )
        evidence = {
            "historical_context": {
                "status": "ANALYZED",
                "historical_comparisons": [{
                    "product": "Mouse Pad",
                    "status": "COMPARISON_AVAILABLE",
                    "percentage_change_from_average": 30.0,
                    "threshold_exceeded": True
                }]
            },
            "financial_validation": {"status": "VALID", "total_consistent": True}
        }
        sanitized = post_validate_review(accusatory_review, evidence)
        self.assertNotIn("fraud", sanitized.explanation.lower())
        self.assertNotIn("scam", sanitized.findings[0].explanation.lower())
        self.assertIn("verification", sanitized.findings[0].explanation.lower())

        # 2. Pipeline Retry: Extraction is NOT repeated if Stage 1 already completed
        mock_db = MagicMock()
        mock_inv = MagicMock()
        mock_inv.pipeline_status = PipelineStatus.FAILED
        mock_inv.extraction_completed_at = datetime.now(timezone.utc)
        mock_inv.vendor_name = "Acme Supplies"
        mock_inv.customer_name = "Mock Customer Ltd"
        mock_inv.invoice_number = "INV-001"
        mock_inv.invoice_date = datetime(2026, 3, 1, tzinfo=timezone.utc)
        mock_inv.items = [
            MagicMock(description="Item 1", quantity=Decimal("1"), unit_price=Decimal("100"), tax_rate=Decimal("0.1"), line_total=Decimal("100"))
        ]
        mock_inv.subtotal = Decimal("100")
        mock_inv.tax_amount = Decimal("10")
        mock_inv.total_amount = Decimal("110")
        mock_inv.currency = "USD"
        mock_inv.source_file_path = "mock.pdf"

        with patch('app.api.endpoints.invoices.crud_invoice') as mock_crud, \
             patch('app.api.endpoints.invoices.extract_invoice') as mock_extract, \
             patch('app.api.endpoints.invoices.review_invoice_with_llm') as mock_review, \
             patch('app.api.endpoints.invoices.os.path.exists', return_value=True):

            mock_crud.get_invoice.return_value = mock_inv
            mock_crud.update_invoice.return_value = mock_inv
            mock_review.return_value = {
                "status": "NORMAL",
                "review_recommendation": "NO_ACTION_REQUIRED",
                "findings": [],
                "explanation": "Valid."
            }

            extract_invoice_data(invoice_id=999, db=mock_db)

            # extract_invoice (Stage 1) MUST NOT have been called because Stage 1 was already completed!
            mock_extract.assert_not_called()
            # Stage 3 review was called as part of retry
            mock_review.assert_called_once()
            self.assertEqual(mock_inv.pipeline_status, PipelineStatus.SUCCESS)

if __name__ == '__main__':
    unittest.main()
