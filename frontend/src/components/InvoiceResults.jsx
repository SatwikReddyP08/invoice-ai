import React, { useState } from 'react';
import './InvoiceResults.css';

const InvoiceResults = ({ data, onReset }) => {
  const [currentData, setCurrentData] = useState(data);
  const [disposition, setDisposition] = useState(
    data?.human_disposition?.disposition || data?.review_result?.human_disposition?.disposition || 'ACKNOWLEDGED'
  );
  const [notes, setNotes] = useState(
    data?.human_disposition?.notes || data?.review_result?.human_disposition?.notes || ''
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitMessage, setSubmitMessage] = useState(null);
  const [isDownloading, setIsDownloading] = useState(false);

  if (!currentData) return null;

  const handleSaveDisposition = async () => {
    setIsSubmitting(true);
    setSubmitMessage(null);
    try {
      const res = await fetch(`/api/v1/invoices/${currentData.id}/disposition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disposition, notes })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to update review disposition');
      }
      const updated = await res.json();
      setCurrentData(updated);
      setSubmitMessage({ type: 'success', text: `Reviewer disposition recorded as: ${disposition}` });
    } catch (err) {
      setSubmitMessage({ type: 'error', text: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDownloadReport = async () => {
    setIsDownloading(true);
    try {
      const res = await fetch(`/api/v1/invoices/${currentData.id}/report`);
      if (!res.ok) throw new Error('Failed to generate review audit report');
      const reportData = await res.json();
      const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `InVoice_Audit_Report_${currentData.invoice_number || currentData.id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Report download failed: ${err.message}`);
    } finally {
      setIsDownloading(false);
    }
  };

  const formatCurrency = (amount, currencyCode) => {
    if (amount === null || amount === undefined) return 'N/A';
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currencyCode || 'USD'
      }).format(amount);
    } catch {
      return `${currencyCode || 'USD'} ${amount.toFixed(2)}`;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      }).format(new Date(dateString));
    } catch {
      return dateString;
    }
  };

  const formatPercent = (rate) => {
    if (rate === null || rate === undefined) return 'N/A';
    return `${(rate * 100).toFixed(2)}%`;
  };

  const pipeline = currentData.pipeline_status || 'UNKNOWN';
  const isSuccess = pipeline === 'SUCCESS';
  
  const extractionMeta = currentData.extraction_metadata || currentData.review_result?.extraction_metadata || currentData.financial_validation?.extraction_metadata;
  const isNonLLM = extractionMeta?.extraction_method === 'NON_LLM';
  const extractionMethodLabel = isNonLLM
    ? 'Non-LLM (Deterministic PyMuPDF Engine - Experimental)'
    : 'LLM-Assisted (Groq / Qwen Vision - Production Primary)';
  const humanDisp = currentData.human_disposition || currentData.review_result?.human_disposition;

  return (
    <div className="invoice-results-container">
      <div className="pipeline-container">
        <h3>Invoice Processing Pipeline</h3>
        <div className="pipeline-steps">
          <div className={`pipeline-step ${isSuccess ? 'completed' : ''}`}>
            <span className="step-icon">{isSuccess ? '✓' : '○'}</span>
            <div className="step-content">
              <h4>1. Document Understanding</h4>
              <p>{isNonLLM ? 'PyMuPDF layout extraction' : 'Groq/Qwen vision extraction'}</p>
            </div>
          </div>
          <div className="step-connector">↓</div>
          <div className={`pipeline-step ${isSuccess ? 'completed' : ''}`}>
            <span className="step-icon">{isSuccess ? '✓' : '○'}</span>
            <div className="step-content">
              <h4>2. Financial Analysis</h4>
              <p>Deterministic validation + history</p>
            </div>
          </div>
          <div className="step-connector">↓</div>
          <div className={`pipeline-step ${isSuccess ? 'completed' : ''}`}>
            <span className="step-icon">{isSuccess ? '✓' : '○'}</span>
            <div className="step-content">
              <h4>3. AI Invoice Review</h4>
              <p>LLM evidence interpretation</p>
            </div>
          </div>
          <div className="step-connector">↓</div>
          <div className={`pipeline-step ${isSuccess ? 'completed' : ''}`}>
            <span className="step-icon">{isSuccess ? '✓' : '○'}</span>
            <div className="step-content">
              <h4>4. Final Result</h4>
            </div>
          </div>
        </div>
      </div>

      <div className="invoice-header" style={{ marginTop: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0 }}>Invoice #{currentData.invoice_number || currentData.id}</h2>
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.4rem', alignItems: 'center' }}>
            <span style={{ fontSize: '0.82rem', padding: '0.2rem 0.6rem', borderRadius: '12px', background: isNonLLM ? 'rgba(168, 85, 247, 0.15)' : 'rgba(99, 102, 241, 0.15)', color: isNonLLM ? '#c084fc' : '#818cf8', border: isNonLLM ? '1px solid rgba(168, 85, 247, 0.3)' : '1px solid rgba(99, 102, 241, 0.3)', fontWeight: 600 }}>
              Mode: {extractionMethodLabel}
            </span>
            {extractionMeta?.processing_time_seconds && (
              <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                ({extractionMeta.processing_time_seconds}s)
              </span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {humanDisp ? (
            <span style={{
              fontSize: '0.85rem',
              fontWeight: 700,
              padding: '0.35rem 0.75rem',
              borderRadius: '8px',
              background: humanDisp.disposition === 'RESOLVED' ? 'rgba(16, 185, 129, 0.2)' : humanDisp.disposition === 'NEEDS_FOLLOW_UP' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(59, 130, 246, 0.2)',
              color: humanDisp.disposition === 'RESOLVED' ? '#34d399' : humanDisp.disposition === 'NEEDS_FOLLOW_UP' ? '#fbbf24' : '#60a5fa',
              border: `1px solid ${humanDisp.disposition === 'RESOLVED' ? 'rgba(16, 185, 129, 0.4)' : humanDisp.disposition === 'NEEDS_FOLLOW_UP' ? 'rgba(245, 158, 11, 0.4)' : 'rgba(59, 130, 246, 0.4)'}`
            }}>
              Reviewer: {humanDisp.disposition}
            </span>
          ) : (
            <span className="status-badge success">
              {pipeline}
            </span>
          )}
        </div>
      </div>

      <div className="invoice-grid">
        <div className="info-group">
          <label>Invoice Number</label>
          <p>{currentData.invoice_number || 'N/A'}</p>
        </div>
        <div className="info-group">
          <label>Invoice Date</label>
          <p>{formatDate(currentData.invoice_date)}</p>
        </div>
        <div className="info-group">
          <label>Vendor Name</label>
          <p>{currentData.vendor_name || 'N/A'}</p>
        </div>
        <div className="info-group">
          <label>Customer Name</label>
          <p>{currentData.customer_name || 'N/A'}</p>
        </div>
      </div>

      <div className="financial-summary" style={{ marginTop: '2rem' }}>
        <h3>Financial Summary</h3>
        <div className="summary-row">
          <span>Subtotal:</span>
          <span>{formatCurrency(currentData.subtotal, currentData.currency)}</span>
        </div>
        <div className="summary-row">
          <span>Tax Amount:</span>
          <span>{formatCurrency(currentData.tax_amount, currentData.currency)}</span>
        </div>
        <div className="summary-row grand-total">
          <span>Total Amount:</span>
          <span>{formatCurrency(currentData.total_amount, currentData.currency)}</span>
        </div>
      </div>

      <div className="items-section">
        <h3>Line Items</h3>
        {(!currentData.items || currentData.items.length === 0) ? (
          <p className="empty-items">No line items extracted.</p>
        ) : (
          <div className="table-responsive">
            <table className="items-table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th className="text-right">Quantity</th>
                  <th className="text-right">Unit Price</th>
                  <th className="text-right">Tax Rate</th>
                  <th className="text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {currentData.items.map((item, index) => (
                  <tr key={item.id || index}>
                    <td>{item.description || 'N/A'}</td>
                    <td className="text-right">{item.quantity ?? 'N/A'}</td>
                    <td className="text-right">{formatCurrency(item.unit_price, currentData.currency)}</td>
                    <td className="text-right">{formatPercent(item.tax_rate)}</td>
                    <td className="text-right">{formatCurrency(item.line_total, currentData.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {currentData.financial_validation && (
        <div className="analysis-section">
          <h3>Financial Validation (Stage 2 Deterministic)</h3>
          <div className="analysis-card">
            {currentData.financial_validation.total_consistent ? (
              <>
                <p style={{ color: 'var(--success-color)' }}>✓ Line items match subtotal arithmetic</p>
                <p style={{ color: 'var(--success-color)' }}>✓ Tax calculation is verified consistent</p>
                <p style={{ color: 'var(--success-color)' }}>✓ Total amount matches subtotal + tax</p>
              </>
            ) : (
              <div className="warning">
                <h4>⚠ Arithmetic Discrepancy Detected</h4>
                <p>Invoice total stated: {formatCurrency(currentData.total_amount, currentData.currency)}</p>
                <p>Calculated total (Subtotal + Tax): {formatCurrency(currentData.financial_validation.calculated_total, currentData.currency)}</p>
                <p>Discrepancy: {formatCurrency(currentData.financial_validation.difference, currentData.currency)}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {currentData.historical_context && (
        <div className="analysis-section">
          <h3>Historical Price Context (Same-Vendor Baseline)</h3>
          <div className="analysis-card">
            {currentData.historical_context.status === 'INSUFFICIENT_EVIDENCE' ? (
              <div style={{ padding: '0.75rem', background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', borderRadius: '8px' }}>
                <p style={{ margin: 0, color: '#93c5fd' }}>
                  ℹ <strong>Insufficient Historical Evidence:</strong> {currentData.historical_context.message || 'No prior invoices from this vendor were available with matching currency and strictly prior dates. A price variance cannot be checked.'}
                </p>
              </div>
            ) : (
              <>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
                  Eligible prior invoices analyzed: <strong>{currentData.historical_context.total_historical_invoices}</strong> (same vendor, strictly prior date, matching currency)
                </p>
                {currentData.historical_context.historical_comparisons && currentData.historical_context.historical_comparisons.length > 0 ? (
                  currentData.historical_context.historical_comparisons.map((comp, idx) => {
                    const isDecrease = comp.is_price_decrease || comp.percentage_change_from_previous < 0;
                    const isActionable = comp.is_actionable_increase || comp.change_category?.includes('INCREASE');
                    return (
                      <div key={idx} style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                          <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#f8fafc' }}>{comp.product}</h4>
                          <span style={{
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            padding: '0.2rem 0.6rem',
                            borderRadius: '12px',
                            background: isActionable ? 'rgba(239, 68, 68, 0.15)' : isDecrease ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.1)',
                            color: isActionable ? '#fca5a5' : isDecrease ? '#6ee7b7' : '#e2e8f0',
                            border: isActionable ? '1px solid rgba(239, 68, 68, 0.3)' : isDecrease ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid var(--border-color)'
                          }}>
                            {comp.change_category} {isDecrease ? '(Informational)' : ''}
                          </span>
                        </div>
                        {comp.status === 'INSUFFICIENT_EVIDENCE' ? (
                          <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{comp.message}</p>
                        ) : (
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', fontSize: '0.88rem' }}>
                            <div>
                              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Current Unit Price</div>
                              <div style={{ fontWeight: 700, fontSize: '1rem', color: '#f8fafc' }}>{formatCurrency(comp.current_unit_price, currentData.currency)}</div>
                            </div>
                            <div>
                              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Latest Previous Price</div>
                              <div>{formatCurrency(comp.latest_previous_unit_price, currentData.currency)}</div>
                              <div style={{ fontSize: '0.8rem', color: comp.percentage_change_from_previous > 0 ? '#f87171' : '#34d399', fontWeight: 600 }}>
                                {comp.percentage_change_from_previous > 0 ? '+' : ''}{comp.percentage_change_from_previous}% vs previous
                              </div>
                            </div>
                            <div>
                              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Historical Average</div>
                              <div>{formatCurrency(comp.historical_average_unit_price, currentData.currency)}</div>
                              <div style={{ fontSize: '0.8rem', color: comp.percentage_change_from_average > 0 ? '#f87171' : '#34d399', fontWeight: 600 }}>
                                {comp.percentage_change_from_average > 0 ? '+' : ''}{comp.percentage_change_from_average}% vs average
                              </div>
                            </div>
                            <div>
                              <div style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Sample Size & Outliers</div>
                              <div>N = {comp.sample_size} prior records</div>
                              <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                                {comp.outliers_detected?.length > 0 ? `Outliers: ${comp.outliers_detected.join(', ')}` : 'No outliers detected'}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                ) : (
                  <p>No valid product comparisons found.</p>
                )}
                {currentData.historical_context.is_duplicate_invoice && (
                  <div className="warning" style={{ marginTop: '1rem', padding: '0.75rem', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.5)', borderRadius: '8px' }}>
                    <h4 style={{ margin: '0 0 0.25rem 0', color: '#fbbf24' }}>⚠ Duplicate Submission Detected</h4>
                    <p style={{ margin: 0, fontSize: '0.85rem' }}>An invoice with this vendor name and invoice number has been processed previously. Excluded from baseline to prevent self-referential bias.</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {currentData.review_result && (
        <div className="analysis-section">
          <h3>AI Invoice Review (Stage 3 Evidence Interpretation)</h3>
          <div className={`analysis-card ${currentData.review_result.status === 'REVIEW_RECOMMENDED' ? 'warning' : ''}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '1rem' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Review Recommendation</h4>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: currentData.review_result.review_recommendation === 'REVIEW_RECOMMENDED' ? '#fbbf24' : (currentData.review_result.review_recommendation === 'NO_ACTION_REQUIRED' ? '#34d399' : '#93c5fd'), marginTop: '0.2rem' }}>
                  {currentData.review_result.review_recommendation === 'REVIEW_RECOMMENDED' ? '⚠ REVIEW RECOMMENDED' : (currentData.review_result.review_recommendation === 'NO_ACTION_REQUIRED' ? '✓ NO ACTION REQUIRED' : 'ℹ INSUFFICIENT DATA')}
                </div>
              </div>
              <div>
                <span style={{ fontSize: '0.8rem', padding: '0.25rem 0.6rem', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.08)', color: '#cbd5e1' }}>
                  Pipeline Status: {currentData.review_result.status}
                </span>
              </div>
            </div>
            
            <h4 style={{ marginTop: '1.25rem', marginBottom: '0.5rem' }}>Deterministic Evidence Findings</h4>
            {currentData.review_result.findings && currentData.review_result.findings.length > 0 ? (
              currentData.review_result.findings.map((finding, idx) => {
                const isHigh = finding.severity === 'HIGH';
                const isMed = finding.severity === 'MEDIUM';
                const borderColor = isHigh ? '#ef4444' : isMed ? '#fbbf24' : '#3b82f6';
                return (
                  <div key={idx} style={{ marginTop: '0.75rem', padding: '0.75rem 1rem', background: 'rgba(255, 255, 255, 0.03)', borderLeft: `4px solid ${borderColor}`, borderRadius: '0 8px 8px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ color: '#f8fafc' }}>{finding.type}</strong>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: borderColor }}>
                        SEVERITY: {finding.severity}
                      </span>
                    </div>
                    {finding.product && <div style={{ fontSize: '0.85rem', color: '#93c5fd', marginTop: '0.2rem' }}>Product: {finding.product}</div>}
                    <p style={{ margin: '0.35rem 0 0.15rem 0', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      <strong>Evidence:</strong> {finding.evidence}
                    </p>
                    <p style={{ margin: '0.15rem 0 0 0', fontSize: '0.88rem' }}>
                      <strong>Interpretation:</strong> {finding.explanation}
                    </p>
                  </div>
                );
              })
            ) : (
              <p>No findings reported.</p>
            )}

            <h4 style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>Overall Decision Explanation</h4>
            <p style={{ lineHeight: 1.5, background: 'rgba(255, 255, 255, 0.03)', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--border-color)', margin: 0 }}>
              {currentData.review_result.explanation}
            </p>
          </div>
        </div>
      )}

      {/* Human Review Desk (Workflow & Disposition) */}
      <div className="analysis-section" style={{ marginTop: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0 }}>Human Review Desk</h3>
          <button
            onClick={handleDownloadReport}
            disabled={isDownloading}
            style={{
              background: 'rgba(99, 102, 241, 0.15)',
              color: '#818cf8',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              borderRadius: '8px',
              padding: '0.5rem 1rem',
              fontSize: '0.88rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem'
            }}
          >
            {isDownloading ? 'Generating...' : '📥 Download Audit Report (JSON)'}
          </button>
        </div>

        <div className="analysis-card" style={{ background: 'rgba(15, 23, 42, 0.6)', border: '1px solid var(--border-color)' }}>
          {humanDisp ? (
            <div style={{ marginBottom: '1.25rem', padding: '1rem', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', borderLeft: `4px solid ${humanDisp.disposition === 'RESOLVED' ? '#10b981' : humanDisp.disposition === 'NEEDS_FOLLOW_UP' ? '#f59e0b' : '#3b82f6'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: '#f8fafc', fontSize: '1rem' }}>
                  Recorded Disposition: {humanDisp.disposition}
                </span>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {humanDisp.updated_at ? formatDate(humanDisp.updated_at) : 'Just recorded'}
                </span>
              </div>
              {humanDisp.notes && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem', color: '#cbd5e1' }}>
                  <strong>Reviewer Notes:</strong> {humanDisp.notes}
                </p>
              )}
            </div>
          ) : (
            <div style={{ marginBottom: '1.25rem', padding: '0.75rem 1rem', background: 'rgba(245, 158, 11, 0.08)', borderRadius: '8px', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
              <p style={{ margin: 0, fontSize: '0.88rem', color: '#fbbf24' }}>
                ⏳ <strong>Pending Human Disposition:</strong> No human reviewer disposition has been recorded for this invoice yet. Review the deterministic findings and AI review above, then record your decision below.
              </p>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', alignItems: 'flex-start' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600 }}>
                Select Reviewer Disposition:
              </label>
              <select
                value={disposition}
                onChange={(e) => setDisposition(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  background: 'rgba(30, 41, 59, 0.8)',
                  color: '#f8fafc',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.9rem',
                  outline: 'none'
                }}
              >
                <option value="ACKNOWLEDGED">ACKNOWLEDGED (Findings noted; proceed per standard flow)</option>
                <option value="NEEDS_FOLLOW_UP">NEEDS_FOLLOW_UP (Requires vendor or procurement clarification)</option>
                <option value="RESOLVED">RESOLVED (Exception verified, approved, and cleared)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.4rem', fontWeight: 600 }}>
                Reviewer Justification Note (Optional):
              </label>
              <input
                type="text"
                placeholder="e.g., Price increase verified against renewed master agreement."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                style={{
                  width: '100%',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '8px',
                  background: 'rgba(30, 41, 59, 0.8)',
                  color: '#f8fafc',
                  border: '1px solid var(--border-color)',
                  fontSize: '0.9rem',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', alignItems: 'center' }}>
            {submitMessage && (
              <span style={{
                fontSize: '0.85rem',
                color: submitMessage.type === 'success' ? '#34d399' : '#f87171',
                marginRight: 'auto'
              }}>
                {submitMessage.text}
              </span>
            )}
            <button
              onClick={handleSaveDisposition}
              disabled={isSubmitting}
              style={{
                background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                padding: '0.65rem 1.25rem',
                fontSize: '0.9rem',
                fontWeight: 600,
                cursor: 'pointer',
                opacity: isSubmitting ? 0.7 : 1
              }}
            >
              {isSubmitting ? 'Saving...' : 'Record Human Disposition'}
            </button>
          </div>
        </div>
      </div>

      <div className="actions-section" style={{ marginTop: '2rem' }}>
        <button className="reset-btn" onClick={onReset}>
          Process Another Invoice
        </button>
      </div>
    </div>
  );
};

export default InvoiceResults;
