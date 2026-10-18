import React, { useState, useEffect } from 'react';
import './ReviewDesk.css';

const ReviewDesk = ({ onSelectInvoice }) => {
  const [filter, setFilter] = useState('needs_attention'); // 'needs_attention' | 'completed' | 'informational' | 'all'
  const [invoices, setInvoices] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchInvoices = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/invoices/?review_filter=${filter}&limit=100`);
      if (!res.ok) throw new Error('Failed to load review queue');
      const data = await res.json();
      setInvoices(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, [filter]);

  const formatCurrency = (amount, currencyCode) => {
    if (amount === null || amount === undefined) return '—';
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currencyCode || 'USD'
      }).format(amount);
    } catch {
      return `${currencyCode || 'USD'} ${Number(amount).toFixed(2)}`;
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '—';
    try {
      return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }).format(new Date(dateString));
    } catch {
      return dateString;
    }
  };

  const handleDownloadReport = async (inv, e) => {
    e.stopPropagation();
    try {
      const res = await fetch(`/api/v1/invoices/${inv.id}/report`);
      if (!res.ok) throw new Error('Failed to generate report');
      const reportData = await res.json();
      const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `InVoice_Audit_Report_${inv.invoice_number || inv.id}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Report download failed: ${err.message}`);
    }
  };

  return (
    <div className="review-desk-container">
      <div className="review-desk-header">
        <div>
          <h2>Invoice Review Desk</h2>
          <p className="review-desk-subtitle">
            Focused triage desk separating deterministic findings, AI interpretations, and human reviewer dispositions.
          </p>
        </div>
        <button className="refresh-btn" onClick={fetchInvoices} disabled={isLoading}>
          {isLoading ? 'Refreshing...' : '🔄 Refresh Queue'}
        </button>
      </div>

      {/* Queue Filter Tabs */}
      <div className="queue-filter-tabs">
        <button
          className={`queue-tab ${filter === 'needs_attention' ? 'active attention' : ''}`}
          onClick={() => setFilter('needs_attention')}
        >
          ⚠ Needs Attention
        </button>
        <button
          className={`queue-tab ${filter === 'completed' ? 'active' : ''}`}
          onClick={() => setFilter('completed')}
        >
          ✓ Completed Reviews
        </button>
        <button
          className={`queue-tab ${filter === 'informational' ? 'active' : ''}`}
          onClick={() => setFilter('informational')}
        >
          ℹ Informational / Normal
        </button>
        <button
          className={`queue-tab ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All Invoices
        </button>
      </div>

      {/* Queue Content */}
      {isLoading ? (
        <div className="loading-box">
          <span className="spinner"></span> Loading review queue...
        </div>
      ) : error ? (
        <div className="message-box error">
          <h4>Failed to load review queue</h4>
          <p>{error}</p>
        </div>
      ) : invoices.length === 0 ? (
        <div className="empty-queue-box">
          <span style={{ fontSize: '2rem' }}>🎉</span>
          <h4>No Invoices Found in This Queue</h4>
          <p style={{ color: 'var(--text-secondary)', margin: '0.5rem 0 0 0' }}>
            {filter === 'needs_attention'
              ? 'All invoices requiring review have been resolved or acknowledged.'
              : 'No invoices currently match the selected queue filter.'}
          </p>
        </div>
      ) : (
        <div className="review-table-wrapper">
          <table className="review-table">
            <thead>
              <tr>
                <th>Invoice #</th>
                <th>Vendor</th>
                <th>Customer</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Mode</th>
                <th>AI Review</th>
                <th>Human Disposition</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((inv) => {
                const extractionMeta = inv.extraction_metadata || inv.review_result?.extraction_metadata || inv.financial_validation?.extraction_metadata;
                const isNonLLM = extractionMeta?.extraction_method === 'NON_LLM';
                const rr = inv.review_result || {};
                const rec = rr.review_recommendation;
                const humanDisp = inv.human_disposition || rr.human_disposition;

                return (
                  <tr key={inv.id} onClick={() => onSelectInvoice(inv)} className="clickable-row">
                    <td style={{ fontWeight: 700, color: '#f8fafc' }}>
                      #{inv.invoice_number || inv.id}
                    </td>
                    <td>{inv.vendor_name || <em style={{ color: '#64748b' }}>Unextracted</em>}</td>
                    <td>{inv.customer_name || <em style={{ color: '#64748b' }}>Unextracted</em>}</td>
                    <td>{formatDate(inv.invoice_date)}</td>
                    <td style={{ fontWeight: 600 }}>
                      {formatCurrency(inv.total_amount, inv.currency)}
                    </td>
                    <td>
                      <span className={`method-badge ${isNonLLM ? 'non-llm' : 'llm'}`}>
                        {isNonLLM ? 'Non-LLM' : 'LLM Vision'}
                      </span>
                    </td>
                    <td>
                      <span className={`rec-badge ${rec === 'REVIEW_RECOMMENDED' ? 'recommended' : (rec === 'NO_ACTION_REQUIRED' ? 'normal' : 'insufficient')}`}>
                        {rec === 'REVIEW_RECOMMENDED' ? '⚠ Review Needed' : (rec === 'NO_ACTION_REQUIRED' ? '✓ Normal' : 'ℹ Insufficient')}
                      </span>
                    </td>
                    <td>
                      {humanDisp ? (
                        <span className={`disp-badge ${humanDisp.disposition.toLowerCase()}`}>
                          {humanDisp.disposition}
                        </span>
                      ) : (
                        <span className="disp-badge pending">
                          Pending
                        </span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        <button
                          className="btn-review"
                          onClick={() => onSelectInvoice(inv)}
                          title="Open full invoice inspection and reviewer disposition"
                        >
                          Review
                        </button>
                        <button
                          className="btn-report"
                          onClick={(e) => handleDownloadReport(inv, e)}
                          title="Download formal audit report (JSON)"
                        >
                          Report
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default ReviewDesk;
