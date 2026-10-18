from pydantic import BaseModel

class UploadResponse(BaseModel):
    invoice_id: int
    original_filename: str
    stored_filename: str
    mime_type: str
    size: int
    status: str
