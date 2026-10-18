import os
import json
import io
import fitz # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import pyarrow.parquet as pq

DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
INVOICES_DIR = os.path.join(DATASET_DIR, "invoices")
GROUND_TRUTH_DIR = os.path.join(DATASET_DIR, "ground_truth")

os.makedirs(INVOICES_DIR, exist_ok=True)
os.makedirs(GROUND_TRUTH_DIR, exist_ok=True)

def prepare_dataset():
    print("Preparing comprehensive Stage 1 Document AI evaluation dataset...")

    # -------------------------------------------------------------
    # 1. doc_01_digital_tech.pdf (From storage/test_invoice.pdf)
    # -------------------------------------------------------------
    src_1 = os.path.join("storage", "test_invoice.pdf")
    dst_1 = os.path.join(INVOICES_DIR, "doc_01_digital_tech.pdf")
    if os.path.exists(src_1):
        with open(src_1, "rb") as f_in, open(dst_1, "wb") as f_out:
            f_out.write(f_in.read())
    gt_1 = {
        "doc_id": "doc_01_digital_tech",
        "doc_type": "digital_pdf",
        "invoice_number": "INV-2026-001",
        "vendor_name": "Acme Office Supplies Pvt. Ltd.",
        "invoice_date": "2026-09-15",
        "customer_name": "Example Technologies Pvt. Ltd.",
        "currency": "INR",
        "subtotal": 6400.0,
        "tax_amount": 1152.0,
        "total_amount": 7552.0,
        "items": [
            {"description": "Laptop Stand", "quantity": 2.0, "unit_price": 1500.0, "tax_rate": 0.18, "line_total": 3000.0},
            {"description": "Wireless Keyboard", "quantity": 1.0, "unit_price": 2200.0, "tax_rate": 0.18, "line_total": 2200.0},
            {"description": "USB-C Cable", "quantity": 3.0, "unit_price": 400.0, "tax_rate": 0.18, "line_total": 1200.0}
        ]
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_01_digital_tech.json"), "w") as f:
        json.dump(gt_1, f, indent=2)

    # -------------------------------------------------------------
    # 2. doc_02_digital_ergonomics.pdf (From storage/001cebb4e1ec4d9fa6b8b6beba4aa3ba.pdf)
    # -------------------------------------------------------------
    src_2 = os.path.join("storage", "001cebb4e1ec4d9fa6b8b6beba4aa3ba.pdf")
    dst_2 = os.path.join(INVOICES_DIR, "doc_02_digital_ergonomics.pdf")
    if os.path.exists(src_2):
        with open(src_2, "rb") as f_in, open(dst_2, "wb") as f_out:
            f_out.write(f_in.read())
    gt_2 = {
        "doc_id": "doc_02_digital_ergonomics",
        "doc_type": "digital_pdf",
        "invoice_number": "INV-2026-002",
        "vendor_name": "Nova Workspace Solutions Pvt. Ltd.",
        "invoice_date": "2026-09-28",
        "customer_name": "Apex Digital Systems Pvt. Ltd.",
        "currency": "INR",
        "subtotal": 13000.0,
        "tax_amount": 2340.0,
        "total_amount": 15340.0,
        "items": [
            {"description": "Ergonomic Mouse Pad", "quantity": 4.0, "unit_price": 650.0, "tax_rate": 0.18, "line_total": 2600.0},
            {"description": "HD Web Camera (1080p)", "quantity": 2.0, "unit_price": 3400.0, "tax_rate": 0.18, "line_total": 6800.0},
            {"description": "Multi-Port USB Hub", "quantity": 3.0, "unit_price": 1200.0, "tax_rate": 0.18, "line_total": 3600.0}
        ]
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_02_digital_ergonomics.json"), "w") as f:
        json.dump(gt_2, f, indent=2)

    # -------------------------------------------------------------
    # 3. doc_03_digital_decimals.pdf (From storage/dc7c433ebdb84091a1e664542edd213a.pdf)
    # -------------------------------------------------------------
    src_3 = os.path.join("storage", "dc7c433ebdb84091a1e664542edd213a.pdf")
    dst_3 = os.path.join(INVOICES_DIR, "doc_03_digital_decimals.pdf")
    if os.path.exists(src_3):
        with open(src_3, "rb") as f_in, open(dst_3, "wb") as f_out:
            f_out.write(f_in.read())
    gt_3 = {
        "doc_id": "doc_03_digital_decimals",
        "doc_type": "digital_pdf",
        "invoice_number": "INV-2026-003",
        "vendor_name": "Nova Workspace Solutions Pvt. Ltd.",
        "invoice_date": "2026-12-15",
        "customer_name": "Apex Digital Systems Pvt. Ltd.",
        "currency": "INR",
        "subtotal": 22750.0,
        "tax_amount": 4095.0,
        "total_amount": 26845.0,
        "items": [
            {"description": "Ergonomic Mouse Pad", "quantity": 4.0, "unit_price": 1137.5, "tax_rate": 0.18, "line_total": 4550.0},
            {"description": "HD Web Camera (1080p)", "quantity": 2.0, "unit_price": 5950.0, "tax_rate": 0.18, "line_total": 11900.0},
            {"description": "Multi-Port USB Hub", "quantity": 3.0, "unit_price": 2100.0, "tax_rate": 0.18, "line_total": 6300.0}
        ]
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_03_digital_decimals.json"), "w") as f:
        json.dump(gt_3, f, indent=2)

    # -------------------------------------------------------------
    # 4. doc_04_scanned_raster.pdf (From storage/test_invoice_final.pdf)
    # -------------------------------------------------------------
    src_4 = os.path.join("storage", "test_invoice_final.pdf")
    dst_4 = os.path.join(INVOICES_DIR, "doc_04_scanned_raster.pdf")
    if os.path.exists(src_4):
        with open(src_4, "rb") as f_in, open(dst_4, "wb") as f_out:
            f_out.write(f_in.read())
    gt_4 = {
        "doc_id": "doc_04_scanned_raster",
        "doc_type": "scanned_pdf",
        "invoice_number": "9999",
        "vendor_name": "Final Test Vendor",
        "invoice_date": None,
        "customer_name": None,
        "currency": "USD",
        "subtotal": None,
        "tax_amount": None,
        "total_amount": 123.45,
        "items": []
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_04_scanned_raster.json"), "w") as f:
        json.dump(gt_4, f, indent=2)

    # -------------------------------------------------------------
    # 5. Public KatanaML Test Parquet Invoices (Convert image bytes to PDF)
    # -------------------------------------------------------------
    parquet_path = os.path.join("evaluation", "data", "katanaml_test.parquet")
    if os.path.exists(parquet_path):
        table = pq.read_table(parquet_path)
        
        # Sample 0 -> doc_05_public_single_item.pdf
        gt_raw_0 = json.loads(table.column("ground_truth")[0].as_py())["gt_parse"]
        img_bytes_0 = table.column("image")[0].as_py()["bytes"]
        img_0 = Image.open(io.BytesIO(img_bytes_0))
        dst_5 = os.path.join(INVOICES_DIR, "doc_05_public_single_item.pdf")
        img_0.save(dst_5, "PDF", resolution=150.0)
        gt_5 = {
            "doc_id": "doc_05_public_single_item",
            "doc_type": "public_dataset",
            "invoice_number": gt_raw_0["header"]["invoice_no"],
            "vendor_name": gt_raw_0["header"]["seller"].split()[0], # e.g. Bradley-Andrade
            "invoice_date": "2015-09-18", # from 09/18/2015
            "customer_name": gt_raw_0["header"]["client"].split(" Unit")[0].strip(), # Castro PLC
            "currency": "USD",
            "subtotal": 889.20,
            "tax_amount": 88.92,
            "total_amount": 978.12,
            "items": [
                {
                    "description": gt_raw_0["items"][0]["item_desc"],
                    "quantity": 2.0,
                    "unit_price": 444.60,
                    "tax_rate": 0.10,
                    "line_total": 889.20
                }
            ]
        }
        with open(os.path.join(GROUND_TRUTH_DIR, "doc_05_public_single_item.json"), "w") as f:
            json.dump(gt_5, f, indent=2)

        # Sample 1 -> doc_06_public_multi_item.pdf
        gt_raw_1 = json.loads(table.column("ground_truth")[1].as_py())["gt_parse"]
        img_bytes_1 = table.column("image")[1].as_py()["bytes"]
        img_1 = Image.open(io.BytesIO(img_bytes_1))
        dst_6 = os.path.join(INVOICES_DIR, "doc_06_public_multi_item.pdf")
        img_1.save(dst_6, "PDF", resolution=150.0)
        gt_6 = {
            "doc_id": "doc_06_public_multi_item",
            "doc_type": "public_dataset",
            "invoice_number": gt_raw_1["header"]["invoice_no"],
            "vendor_name": "Hopkins and Sons",
            "invoice_date": "2021-05-29",
            "customer_name": "Sims PLC",
            "currency": "USD",
            "subtotal": 581.93,
            "tax_amount": 58.19,
            "total_amount": 640.12,
            "items": [
                {
                    "description": it["item_desc"],
                    "quantity": float(it["item_qty"].replace(",", ".")),
                    "unit_price": float(it["item_net_price"].replace(",", ".")),
                    "tax_rate": 0.10,
                    "line_total": float(it["item_net_worth"].replace(",", "."))
                } for it in gt_raw_1["items"]
            ]
        }
        with open(os.path.join(GROUND_TRUTH_DIR, "doc_06_public_multi_item.json"), "w") as f:
            json.dump(gt_6, f, indent=2)

    # -------------------------------------------------------------
    # 6. doc_07_multipage_spanning.pdf (2-page Digital PDF table spanning pages)
    # -------------------------------------------------------------
    doc_multi = fitz.open()
    # Page 1
    page1 = doc_multi.new_page(width=595, height=842)
    p1_text = """ENTERPRISE HARDWARE SUPPLIES LTD
100 Industrial Parkway, Tech City
VAT ID: GB-994827104

COMMERCIAL TAX INVOICE
Invoice Number: EHS-2026-9042
Invoice Date: 12 October 2026
Payment Terms: Net 30 Days

BILL TO:
Global Logistics Systems Inc.
450 Terminal Boulevard, Portside

LINE ITEMS (Continued on Page 2):
-----------------------------------------------------------------------------------------
Item Description                               Qty    Unit Price (EUR)   Tax%   Line Total
-----------------------------------------------------------------------------------------
1. Rackmount Server 2U Xeon Scalable             2       4500.00         20%     9000.00
2. Enterprise SSD 3.84TB NVMe U.2               8        520.00         20%     4160.00
3. 64GB DDR5 Registered ECC DIMM               16        210.00         20%     3360.00
4. Dual-Port 25GbE PCIe NIC SFP28                4        380.00         20%     1520.00
5. Redundant 1200W Titanium Hot-Plug PSU         4        290.00         20%     1160.00
-----------------------------------------------------------------------------------------
(Table continues on Page 2)
"""
    page1.insert_text((40, 50), p1_text, fontsize=10)

    # Page 2
    page2 = doc_multi.new_page(width=595, height=842)
    p2_text = """COMMERCIAL TAX INVOICE (Page 2 of 2)
Invoice Number: EHS-2026-9042

LINE ITEMS (Continued from Page 1):
-----------------------------------------------------------------------------------------
Item Description                               Qty    Unit Price (EUR)   Tax%   Line Total
-----------------------------------------------------------------------------------------
6. Cat6A 10Gbps Shielded Patch Cable 2m        20         15.00         20%      300.00
7. 24-Port High-Density Patch Panel              2        140.00         20%      280.00
8. Smart Rack PDU Metered 32A IEC                2        750.00         20%     1500.00
-----------------------------------------------------------------------------------------

FINANCIAL SUMMARY:
Subtotal: EUR 21280.00
Value Added Tax (20% VAT): EUR 4256.00
Total Amount Payable: EUR 25536.00
"""
    page2.insert_text((40, 50), p2_text, fontsize=10)
    dst_7 = os.path.join(INVOICES_DIR, "doc_07_multipage_spanning.pdf")
    doc_multi.save(dst_7)
    doc_multi.close()

    gt_7 = {
        "doc_id": "doc_07_multipage_spanning",
        "doc_type": "multipage_pdf",
        "invoice_number": "EHS-2026-9042",
        "vendor_name": "ENTERPRISE HARDWARE SUPPLIES LTD",
        "invoice_date": "2026-10-12",
        "customer_name": "Global Logistics Systems Inc.",
        "currency": "EUR",
        "subtotal": 21280.0,
        "tax_amount": 4256.0,
        "total_amount": 25536.0,
        "items": [
            {"description": "Rackmount Server 2U Xeon Scalable", "quantity": 2.0, "unit_price": 4500.0, "tax_rate": 0.20, "line_total": 9000.0},
            {"description": "Enterprise SSD 3.84TB NVMe U.2", "quantity": 8.0, "unit_price": 520.0, "tax_rate": 0.20, "line_total": 4160.0},
            {"description": "64GB DDR5 Registered ECC DIMM", "quantity": 16.0, "unit_price": 210.0, "tax_rate": 0.20, "line_total": 3360.0},
            {"description": "Dual-Port 25GbE PCIe NIC SFP28", "quantity": 4.0, "unit_price": 380.0, "tax_rate": 0.20, "line_total": 1520.0},
            {"description": "Redundant 1200W Titanium Hot-Plug PSU", "quantity": 4.0, "unit_price": 290.0, "tax_rate": 0.20, "line_total": 1160.0},
            {"description": "Cat6A 10Gbps Shielded Patch Cable 2m", "quantity": 20.0, "unit_price": 15.0, "tax_rate": 0.20, "line_total": 300.0},
            {"description": "24-Port High-Density Patch Panel", "quantity": 2.0, "unit_price": 140.0, "tax_rate": 0.20, "line_total": 280.0},
            {"description": "Smart Rack PDU Metered 32A IEC", "quantity": 2.0, "unit_price": 750.0, "tax_rate": 0.20, "line_total": 1500.0}
        ]
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_07_multipage_spanning.json"), "w") as f:
        json.dump(gt_7, f, indent=2)

    # -------------------------------------------------------------
    # 7. doc_08_missing_fields.pdf (Missing Customer, Missing Tax)
    # -------------------------------------------------------------
    doc_missing = fitz.open()
    p_missing = doc_missing.new_page(width=595, height=842)
    p_text_missing = """FREELANCE CONSULTING SERVICES
Invoice Ref: CS-2026-771
Invoice Date: 05 August 2026

Description:
Cloud Architecture Advisory (Hours: 25.0)
Hourly Rate: $150.00
Total Due: $3750.00
Tax Exempt / Cross-Border B2B Supply.
Currency: USD
"""
    p_missing.insert_text((50, 60), p_text_missing, fontsize=11)
    dst_8 = os.path.join(INVOICES_DIR, "doc_08_missing_fields.pdf")
    doc_missing.save(dst_8)
    doc_missing.close()

    gt_8 = {
        "doc_id": "doc_08_missing_fields",
        "doc_type": "missing_fields_pdf",
        "invoice_number": "CS-2026-771",
        "vendor_name": "FREELANCE CONSULTING SERVICES",
        "invoice_date": "2026-08-05",
        "customer_name": None,
        "currency": "USD",
        "subtotal": 3750.0,
        "tax_amount": None,
        "total_amount": 3750.0,
        "items": [
            {"description": "Cloud Architecture Advisory", "quantity": 25.0, "unit_price": 150.0, "tax_rate": None, "line_total": 3750.0}
        ]
    }
    with open(os.path.join(GROUND_TRUTH_DIR, "doc_08_missing_fields.json"), "w") as f:
        json.dump(gt_8, f, indent=2)

    print(f"Dataset preparation complete! Created 8 ground-truth annotated evaluation documents.")

if __name__ == "__main__":
    prepare_dataset()
