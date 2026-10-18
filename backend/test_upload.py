import os
import time
import requests
import sys

URL = "http://127.0.0.1:8000/api/v1/invoices/upload"
DB_URL = "http://127.0.0.1:8000/api/v1/invoices"

def wait_for_server():
    for _ in range(10):
        try:
            r = requests.get("http://127.0.0.1:8000/")
            if r.status_code == 200:
                return True
        except:
            time.sleep(1)
    return False

def test():
    if not wait_for_server():
        print("Server didn't start")
        sys.exit(1)
        
    print("1. Creating dummy PDF...")
    pdf_content = b"%PDF-1.4\n%...\n" + b"A" * 1024
    with open("test_invoice.pdf", "wb") as f:
        f.write(pdf_content)
        
    print("2. Uploading valid PDF...")
    with open("test_invoice.pdf", "rb") as f:
        files = {"file": ("test_invoice.pdf", f, "application/pdf")}
        r = requests.post(URL, files=files)
        
    assert r.status_code == 201, f"Failed: {r.text}"
    resp = r.json()
    assert resp["original_filename"] == "test_invoice.pdf"
    assert resp["stored_filename"] != "test_invoice.pdf"
    assert resp["mime_type"] == "application/pdf"
    assert resp["status"] == "PENDING"
    
    inv_id = resp["invoice_id"]
    stored_filename = resp["stored_filename"]
    
    print("3. Verifying file exists in storage...")
    storage_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", stored_filename)
    assert os.path.exists(storage_path)
    
    print("4. Verifying DB record...")
    r = requests.get(f"{DB_URL}/{inv_id}")
    assert r.status_code == 200
    db_inv = r.json()
    assert db_inv["source_file_path"] == stored_filename
    assert db_inv["pipeline_status"] == "PENDING"
    
    print("5. Testing unsupported file type (txt disguised as pdf)...")
    txt_content = b"This is just a text file."
    with open("fake.pdf", "wb") as f:
        f.write(txt_content)
        
    with open("fake.pdf", "rb") as f:
        files = {"file": ("fake.pdf", f, "application/pdf")}
        r = requests.post(URL, files=files)
    assert r.status_code == 400
    assert "Unsupported" in r.text
    
    print("6. Testing oversized file (simulated 11MB file)...")
    with open("huge.pdf", "wb") as f:
        f.write(b"%PDF-1.4\n")
        f.seek(11 * 1024 * 1024 - 1)
        f.write(b"0")
        
    with open("huge.pdf", "rb") as f:
        files = {"file": ("huge.pdf", f, "application/pdf")}
        r = requests.post(URL, files=files)
    assert r.status_code == 413, f"Expected 413, got {r.status_code}: {r.text}"
    
    print("7. Cleaning up test data...")
    requests.delete(f"{DB_URL}/{inv_id}")
    os.remove("test_invoice.pdf")
    os.remove("fake.pdf")
    os.remove("huge.pdf")
    if os.path.exists(storage_path):
        os.remove(storage_path)
        
    print("SUCCESS")

if __name__ == "__main__":
    test()
