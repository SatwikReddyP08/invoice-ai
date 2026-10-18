import requests
import time
import sys

URL = "http://127.0.0.1:8000/api/v1/invoices"

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
        
    print("1. Creating invoice with multiple items...")
    payload = {
        "invoice_number": "INV-1001",
        "vendor_name": "Test Vendor",
        "source_file_path": "/tmp/test.pdf",
        "items": [
            {"description": "Item 1", "quantity": 2, "unit_price": 10.0},
            {"description": "Item 2", "quantity": 1, "unit_price": 20.0}
        ]
    }
    r = requests.post(f"{URL}/", json=payload)
    assert r.status_code == 201, f"Failed to create: {r.text}"
    inv = r.json()
    inv_id = inv["id"]
    print(f"Created Invoice ID: {inv_id}")
    assert len(inv["items"]) == 2
    
    print("2. Retrieving invoice...")
    r = requests.get(f"{URL}/{inv_id}")
    assert r.status_code == 200
    retrieved = r.json()
    assert retrieved["vendor_name"] == "Test Vendor"
    assert len(retrieved["items"]) == 2
    
    print("3. Updating invoice...")
    update_payload = {
        "vendor_name": "Updated Vendor",
        "items": [
            {"description": "Item 1 Updated", "quantity": 3},
        ]
    }
    r = requests.put(f"{URL}/{inv_id}", json=update_payload)
    assert r.status_code == 200, f"Failed to update: {r.text}"
    updated = r.json()
    assert updated["vendor_name"] == "Updated Vendor"
    assert len(updated["items"]) == 1
    assert updated["items"][0]["description"] == "Item 1 Updated"
    
    print("4. Testing duplicate creation (permitted)...")
    payload["invoice_number"] = "INV-1001"
    payload["vendor_name"] = "Updated Vendor"
    r = requests.post(f"{URL}/", json=payload)
    assert r.status_code == 201
    dup_id = r.json()["id"]
    requests.delete(f"{URL}/{dup_id}")
    
    print("5. Listing invoices...")
    r = requests.get(f"{URL}/?limit=10")
    assert r.status_code == 200
    listed = r.json()
    assert listed["total"] >= 1
    assert len(listed["items"]) >= 1
    
    print("6. Deleting invoice...")
    r = requests.delete(f"{URL}/{inv_id}")
    assert r.status_code == 204
    
    print("7. Verifying deletion...")
    r = requests.get(f"{URL}/{inv_id}")
    assert r.status_code == 404
    
    print("SUCCESS")

if __name__ == "__main__":
    test()
