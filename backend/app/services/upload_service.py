import os
import uuid
import filetype
from fastapi import UploadFile, HTTPException
from app.core.config import settings

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png"
}

def save_upload_file(upload_file: UploadFile) -> dict:
    # Read the first chunk to determine file type via magic bytes
    header = upload_file.file.read(2048)
    upload_file.file.seek(0)
    
    kind = filetype.guess(header)
    if kind is None or kind.mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type.")
    
    mime_type = kind.mime
    ext = ALLOWED_MIME_TYPES[mime_type]
    
    # Generate unique secure filename
    filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Ensure storage dir exists
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    
    file_path = os.path.join(settings.STORAGE_DIR, filename)
    
    # Write in chunks to avoid memory issues and enforce size limit
    bytes_written = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = upload_file.file.read(1024 * 1024) # 1MB chunks
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="File too large.")
                f.write(chunk)
    except Exception as e:
        # Cleanup partial file on error
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e
        
    return {
        "filename": upload_file.filename,
        "stored_filename": filename,
        "file_path": file_path,
        "mime_type": mime_type,
        "size": bytes_written
    }
