import React, { useState, useRef } from 'react';
import './UploadInvoice.css';
import InvoiceResults from './InvoiceResults';
import { API_BASE } from '../apiConfig';

const UploadInvoice = ({ onInvoiceProcessed }) => {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const [successData, setSuccessData] = useState(null);
  
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState(null);
  const [extractedData, setExtractedData] = useState(null);

  const fileInputRef = useRef(null);

  const SUPPORTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];
  const MAX_SIZE = 10 * 1024 * 1024; // 10MB

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const validateFile = (selectedFile) => {
    setError(null);
    setSuccessData(null);
    setExtractionError(null);
    setExtractedData(null);

    if (!selectedFile) return false;

    if (!SUPPORTED_TYPES.includes(selectedFile.type)) {
      setError('Unsupported file type. Please upload PDF, PNG, or JPEG.');
      return false;
    }

    if (selectedFile.size > MAX_SIZE) {
      setError('File is too large. Maximum size is 10MB.');
      return false;
    }

    return true;
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedFile = e.dataTransfer.files[0];
      if (validateFile(droppedFile)) {
        setFile(droppedFile);
      }
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      const selectedFile = e.target.files[0];
      if (validateFile(selectedFile)) {
        setFile(selectedFile);
      }
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    setError(null);
    setSuccessData(null);
    setExtractionError(null);
    setExtractedData(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/api/v1/invoices/upload`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to upload invoice');
      }

      const data = await response.json();
      setSuccessData(data);
      setFile(null); // Clear file on success
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setError(err.message || 'An unexpected error occurred during upload.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleExtract = async () => {
    if (!successData || !successData.invoice_id) return;

    setIsExtracting(true);
    setExtractionError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/invoices/${successData.invoice_id}/extract`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to extract invoice data');
      }

      const data = await response.json();
      if (onInvoiceProcessed) {
        onInvoiceProcessed(data);
      } else {
        setExtractedData(data);
      }
    } catch (err) {
      setExtractionError(err.message || 'An unexpected error occurred during invoice processing.');
    } finally {
      setIsExtracting(false);
    }
  };

  const resetFlow = () => {
    setFile(null);
    setSuccessData(null);
    setExtractedData(null);
    setError(null);
    setExtractionError(null);
  };

  if (extractedData) {
    return <InvoiceResults data={extractedData} sourceView="upload" onUploadNew={resetFlow} onReset={resetFlow} />;
  }

  return (
    <div className="upload-container">
      {!file && !successData && (
        <div 
          className={`upload-area ${isDragging ? 'drag-active' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current.click()}
        >
          <svg className="upload-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
          </svg>
          <p className="upload-text">Click or drag invoice to upload</p>
          <p className="upload-hint">PDF, PNG, or JPEG (max. 10MB)</p>
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileSelect} 
            accept=".pdf,image/png,image/jpeg"
            className="file-input" 
          />
        </div>
      )}

      {file && !successData && (
        <div className="file-info">
          <div className="file-details">
            <span className="file-name">{file.name}</span>
            <span className="file-size">{formatFileSize(file.size)}</span>
          </div>
          <button 
            className="upload-btn" 
            onClick={handleUpload} 
            disabled={isUploading}
          >
            {isUploading ? (
              <><span className="loading-spinner"></span> Uploading...</>
            ) : (
              'Upload Invoice'
            )}
          </button>
        </div>
      )}

      {error && (
        <div className="message-box error">
          <h4>Upload Failed</h4>
          <p>{error}</p>
        </div>
      )}

      {successData && (
        <div className="message-box success">
          <h4>Upload Successful</h4>
          <p><strong>Invoice ID:</strong> #{successData.invoice_id}</p>
          <p><strong>Filename:</strong> {successData.original_filename}</p>
          <p><strong>Initial Status:</strong> {successData.status}</p>
          
          <div className="extract-actions" style={{ marginTop: '1.5rem', paddingTop: '1.25rem', borderTop: '1px solid rgba(16, 185, 129, 0.3)' }}>
            <p style={{ marginBottom: '1rem', color: '#e2e8f0', fontSize: '0.92rem' }}>
              Document is staged and ready for the multi-stage AI pipeline (Document Understanding → Deterministic Financial Analysis → AI Invoice Review).
            </p>

            <button 
              className="upload-btn" 
              onClick={handleExtract} 
              disabled={isExtracting}
              style={{ width: '100%' }}
            >
              {isExtracting ? (
                <><span className="loading-spinner"></span> Processing AI Pipeline...</>
              ) : (
                'Process Invoice'
              )}
            </button>
          </div>
        </div>
      )}

      {extractionError && (
        <div className="message-box error" style={{ marginTop: '1rem' }}>
          <h4>Pipeline Processing Failed</h4>
          <p>{extractionError}</p>
        </div>
      )}
    </div>
  );
};

export default UploadInvoice;
