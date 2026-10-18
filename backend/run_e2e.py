import requests
import time
import json
import os

BASE_URL = "http://127.0.0.1:8000/api/v1/invoices"
FILE_PATH = "storage/test_invoice.pdf"

def run():
    print(f"Uploading {FILE_PATH}...")
    if not os.path.exists(FILE_PATH):
        print(f"File not found: {FILE_PATH}")
        return
        
    with open(FILE_PATH, "rb") as f:
        files = {"file": ("test_invoice.pdf", f, "application/pdf")}
        response = requests.post(f"{BASE_URL}/upload", files=files)
        
    if response.status_code != 201:
        print(f"Upload failed: {response.text}")
        return
        
    data = response.json()
    invoice_id = data["invoice_id"]
    print(f"Uploaded successfully. Invoice ID: {invoice_id}")
    
    print("Starting pipeline (extract endpoint)...")
    start_time = time.time()
    response = requests.post(f"{BASE_URL}/{invoice_id}/extract")
    duration = time.time() - start_time
    
    print(f"Extraction took {duration:.2f} seconds.")
    
    if response.status_code != 200:
        print(f"Pipeline failed with status {response.status_code}: {response.text}")
        return
        
    result = response.json()
    print("Pipeline Success!")
    print(f"Pipeline Status: {result.get('pipeline_status')}")
    print(f"Vendor: {result.get('vendor_name')}")
    print(f"Total Amount: {result.get('total_amount')}")
    
    print("\n--- Pipeline Evidence JSON ---")
    print("Financial Validation:")
    print(json.dumps(result.get("financial_validation"), indent=2))
    
    print("\nHistorical Context:")
    print(json.dumps(result.get("historical_context"), indent=2))
    
    print("\nAI Review Result:")
    print(json.dumps(result.get("review_result"), indent=2))

if __name__ == "__main__":
    run()
