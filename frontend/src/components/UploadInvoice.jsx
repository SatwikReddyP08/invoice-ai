import React, { useState, useRef } from 'react';
import './UploadInvoice.css';
import InvoiceResults from './InvoiceResults';
import ExtractionComparison from './ExtractionComparison';

const UploadInvoice = () => {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);
  const [successData, setSuccessData] = useState(null);
  
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractionError, setExtractionError] = useState(null);
  const [extractedData, setExtractedData] = useState(null);

  const [extractionMode, setExtractionMode] = useState('llm'); // 'llm' | 'non_llm' | 'compare'
  const [comparisonData, setComparisonData] = useState(null);

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
    setComparisonData(null);

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
    setComparisonData(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/v1/invoices/upload', {
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

  const handleExtract = async (overrideMode) => {
    if (!successData || !successData.invoice_id) return;
    const modeToRun = overrideMode || extractionMode;

    setIsExtracting(true);
    setExtractionError(null);

    if (modeToRun === 'compare') {
      try {
        const response = await fetch(`/api/v1/invoices/${successData.invoice_id}/compare`, {
          method: 'POST'
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to execute extraction comparison');
        }

        const compResult = await response.json();
        setComparisonData(compResult);
      } catch (err) {
        setExtractionError(err.message || 'Comparison failed.');
      } finally {
        setIsExtracting(false);
      }
      return;
    }

    try {
      const response = await fetch(`/api/v1/invoices/${successData.invoice_id}/extract?mode=${modeToRun}`, {
        method: 'POST'
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to extract invoice data');
      }

      const data = await response.json();
      setExtractedData(data);
      setComparisonData(null);
    } catch (err) {
      setExtractionError(err.message || 'An unexpected error occurred during extraction.');
    } finally {
      setIsExtracting(false);
    }
  };

  const resetFlow = () => {
    setFile(null);
    setSuccessData(null);
    setExtractedData(null);
    setComparisonData(null);
    setError(null);
    setExtractionError(null);
    setExtractionMode('llm');
  };

  if (comparisonData) {
    return (
      <ExtractionComparison
        comparisonData={comparisonData}
        onProceedWithMode={(mode) => handleExtract(mode)}
        onBack={() => setComparisonData(null)}
      />
    );
  }

  if (extractedData) {
    return <InvoiceResults data={extractedData} onReset={resetFlow} />;
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
          <h4>Upload Successful!</h4>
          <p><strong>Invoice ID:</strong> {successData.invoice_id}</p>
          <p><strong>Filename:</strong> {successData.original_filename}</p>
          <p><strong>Status:</strong> {successData.status}</p>
          
          <div className="extract-actions" style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid rgba(16, 185, 129, 0.3)' }}>
            <p style={{ marginBottom: '1rem', color: '#f8fafc', fontWeight: 500 }}>
              Select Document Extraction Architecture:
            </p>
            
            <div className="mode-selector-container">
              {/* Option 1: LLM Assisted */}
              <label className={`mode-card ${extractionMode === 'llm' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_mode"
                  value="llm"
                  checked={extractionMode === 'llm'}
                  onChange={() => setExtractionMode('llm')}
                  disabled={isExtracting}
                />
                <div className="mode-card-content">
                  <div className="mode-card-title-row">
                    <span className="mode-card-title">LLM-Assisted Extraction</span>
                    <span className="mode-tag primary">Production Primary</span>
                  </div>
                  <p className="mode-card-desc">
                    Multi-modal vision model via Groq API (<code>qwen/qwen3.8-27b</code>). Handles complex, digital, and scanned layouts.
                  </p>
                </div>
              </label>

              {/* Option 2: Non-LLM */}
              <label className={`mode-card ${extractionMode === 'non_llm' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_mode"
                  value="non_llm"
                  checked={extractionMode === 'non_llm'}
                  onChange={() => setExtractionMode('non_llm')}
                  disabled={isExtracting}
                />
                <div className="mode-card-content">
                  <div className="mode-card-title-row">
                    <span className="mode-card-title">Non-LLM Deterministic Parser</span>
                    <span className="mode-tag experimental">Experimental Local</span>
                  </div>
                  <p className="mode-card-desc">
                    Spatial layout and coordinate table parser via PyMuPDF. Ultra-fast local execution with zero API cost. Requires digital text.
                  </p>
                </div>
              </label>

              {/* Option 3: Compare Both */}
              <label className={`mode-card ${extractionMode === 'compare' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="extraction_mode"
                  value="compare"
                  checked={extractionMode === 'compare'}
                  onChange={() => setExtractionMode('compare')}
                  disabled={isExtracting}
                />
                <div className="mode-card-content">
                  <div className="mode-card-title-row">
                    <span className="mode-card-title">Side-by-Side Comparison</span>
                    <span className="mode-tag compare">Audit & Benchmark</span>
                  </div>
                  <p className="mode-card-desc">
                    Runs both extraction engines on this document. Inspect header agreement, line-item alignment, and latency side by side.
                  </p>
                </div>
              </label>
            </div>

            <button 
              className="upload-btn" 
              onClick={() => handleExtract()} 
              disabled={isExtracting}
              style={{ width: '100%', marginTop: '0.75rem' }}
            >
              {isExtracting ? (
                <><span className="loading-spinner"></span> {extractionMode === 'compare' ? 'Running Side-by-Side Comparison...' : 'Extracting Invoice Data...'}</>
              ) : (
                extractionMode === 'compare'
                  ? 'Run Side-by-Side Comparison'
                  : extractionMode === 'non_llm'
                  ? 'Process Invoice (Non-LLM Experimental)'
                  : 'Process Invoice (LLM-Assisted)'
              )}
            </button>
          </div>
        </div>
      )}

      {extractionError && (
        <div className="message-box error" style={{ marginTop: '1rem' }}>
          <h4>Extraction Failed</h4>
          <p>{extractionError}</p>
        </div>
      )}
    </div>
  );
};

export default UploadInvoice;
