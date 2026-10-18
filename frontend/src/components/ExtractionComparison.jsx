import React, { useState } from 'react';
import './ExtractionComparison.css';

const ExtractionComparison = ({ comparisonData, onProceedWithMode, onBack }) => {
  const [activeTab, setActiveTab] = useState('headers'); // 'headers' | 'items' | 'financial'

  if (!comparisonData) return null;

  const {
    invoice_id,
    filename,
    llm_result,
    non_llm_result,
    header_field_comparisons,
    line_item_comparisons,
    summary_notes
  } = comparisonData;

  const formatCurrency = (val, curr = 'USD') => {
    if (val === null || val === undefined) return '—';
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: curr || 'USD'
      }).format(val);
    } catch {
      return `${curr} ${Number(val).toFixed(2)}`;
    }
  };

  const speedup = (non_llm_result?.processing_time_seconds > 0 && llm_result?.processing_time_seconds > 0)
    ? (llm_result.processing_time_seconds / non_llm_result.processing_time_seconds).toFixed(1)
    : '—';

  const matchesCount = header_field_comparisons?.filter(c => c.matches).length || 0;
  const totalHeaders = header_field_comparisons?.length || 0;

  return (
    <div className="comparison-container">
      <div className="comparison-header">
        <div className="comparison-title-area">
          <h2>Extraction Method Comparison</h2>
          <p className="comparison-subtitle">
            Document: <strong>{filename}</strong> (Invoice #{invoice_id}) &bull; Isolated Comparison Run
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <span className="mode-badge primary">Production: LLM Vision</span>
          <span className="mode-badge experimental">Experimental: Non-LLM</span>
        </div>
      </div>

      {/* Honest Evaluation & Ground Truth Disclosure */}
      <div className="honest-comparison-banner" style={{
        background: 'rgba(59, 130, 246, 0.1)',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        borderRadius: '12px',
        padding: '1rem 1.25rem',
        marginBottom: '1.5rem',
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'flex-start'
      }}>
        <span style={{ fontSize: '1.25rem', lineHeight: 1 }}>ℹ️</span>
        <div style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: 1.5 }}>
          <strong style={{ color: '#93c5fd' }}>Ground Truth & Benchmark Honesty Notice:</strong> Method agreement measures consistency between the two extraction engines on this specific document; it does <em>not</em> prove factual correctness. Neither method can be declared "more accurate" without an annotated, manually verified reference benchmark. Please review missing fields and discrepancies carefully.
        </div>
      </div>

      {/* 3 Summary Cards */}
      <div className="comparison-cards-grid">
        {/* LLM Card */}
        <div className="method-card llm">
          <div className="method-card-header">
            <div>
              <h3>LLM-Assisted</h3>
              <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Groq / Qwen Vision (qwen/qwen3.8-27b)
              </p>
            </div>
            <span className="mode-badge primary">Primary</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Execution Status:</span>
            <span className={`stat-val ${llm_result.success ? 'success' : 'stat-val'}`}>
              {llm_result.success ? '✓ Succeeded' : 'Failed'}
            </span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Processing Time:</span>
            <span className="stat-val">{llm_result.processing_time_seconds}s</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Line Items Extracted:</span>
            <span className="stat-val">{llm_result.extracted_data?.items?.length || 0} items</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Arithmetic Balance:</span>
            <span className={`stat-val ${llm_result.financial_validation?.total_consistent ? 'success' : ''}`}>
              {llm_result.financial_validation?.total_consistent ? '✓ Balanced' : 'Discrepancy'}
            </span>
          </div>
        </div>

        {/* Non-LLM Card */}
        <div className="method-card non-llm">
          <div className="method-card-header">
            <div>
              <h3>Non-LLM Parser</h3>
              <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                PyMuPDF Deterministic Layout Engine
              </p>
            </div>
            <span className="mode-badge experimental">Experimental</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Execution Status:</span>
            <span className={`stat-val ${non_llm_result.success ? 'success' : 'stat-val'}`}>
              {non_llm_result.success ? '✓ Succeeded' : 'Failed'}
            </span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Processing Time:</span>
            <span className="stat-val">{non_llm_result.processing_time_seconds}s</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Line Items Extracted:</span>
            <span className="stat-val">{non_llm_result.extracted_data?.items?.length || 0} items</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Arithmetic Balance:</span>
            <span className={`stat-val ${non_llm_result.financial_validation?.total_consistent ? 'success' : ''}`}>
              {non_llm_result.financial_validation?.total_consistent ? '✓ Balanced' : 'Discrepancy / Incomplete'}
            </span>
          </div>
        </div>

        {/* Benchmark Delta Card */}
        <div className="method-card benchmark">
          <div className="method-card-header">
            <div>
              <h3>Single-Doc Comparison</h3>
              <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                Per-Document Single Run (Isolated)
              </p>
            </div>
            <span className="mode-badge metric">Differential</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Relative Latency:</span>
            <span className="stat-val speedup">
              {non_llm_result.success && llm_result.success ? `${speedup}x (this doc only)` : 'N/A'}
            </span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Header Agreement:</span>
            <span className="stat-val">{matchesCount} / {totalHeaders} fields</span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Line Item Match:</span>
            <span className="stat-val">
              {line_item_comparisons?.filter(r => r.match_status === 'EXACT_MATCH').length || 0} / {line_item_comparisons?.length || 0} rows
            </span>
          </div>
          <div className="method-stat-row">
            <span className="stat-label">Ground Truth:</span>
            <span className="stat-val" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Requires Manual Verification
            </span>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
        <button
          onClick={() => setActiveTab('headers')}
          style={{
            background: activeTab === 'headers' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            color: activeTab === 'headers' ? '#818cf8' : 'var(--text-secondary)',
            border: activeTab === 'headers' ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
            borderRadius: '8px',
            padding: '0.5rem 1rem',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          Header Fields ({matchesCount}/{totalHeaders} Match)
        </button>
        <button
          onClick={() => setActiveTab('items')}
          style={{
            background: activeTab === 'items' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            color: activeTab === 'items' ? '#818cf8' : 'var(--text-secondary)',
            border: activeTab === 'items' ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
            borderRadius: '8px',
            padding: '0.5rem 1rem',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          Line Items ({line_item_comparisons?.length || 0} Total Rows)
        </button>
        <button
          onClick={() => setActiveTab('financial')}
          style={{
            background: activeTab === 'financial' ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
            color: activeTab === 'financial' ? '#818cf8' : 'var(--text-secondary)',
            border: activeTab === 'financial' ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
            borderRadius: '8px',
            padding: '0.5rem 1rem',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem'
          }}
        >
          Financial Validation Comparison
        </button>
      </div>

      {/* Tab 1: Header Fields Comparison Table */}
      {activeTab === 'headers' && (
        <div className="comparison-section">
          <div className="comparison-table-wrapper">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Field Name</th>
                  <th>LLM-Assisted Value</th>
                  <th>Non-LLM Value</th>
                  <th>Agreement</th>
                  <th>Observation Note</th>
                </tr>
              </thead>
              <tbody>
                {header_field_comparisons.map((item, idx) => (
                  <tr key={idx}>
                    <td className="field-name-cell">{item.field_name.replace(/_/g, ' ')}</td>
                    <td>
                      {item.llm_value !== null && item.llm_value !== undefined ? String(item.llm_value) : <em style={{ color: '#64748b' }}>null</em>}
                    </td>
                    <td>
                      {item.non_llm_value !== null && item.non_llm_value !== undefined ? String(item.non_llm_value) : <em style={{ color: '#64748b' }}>null</em>}
                    </td>
                    <td>
                      <span className={`match-badge ${item.matches ? 'exact' : (item.llm_value && item.non_llm_value ? 'mismatch' : 'missing')}`}>
                        {item.matches ? '✓ Match' : (item.llm_value && item.non_llm_value ? '⚠ Mismatch' : 'Missing')}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                      {item.difference_note}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 2: Line Items Comparison Table */}
      {activeTab === 'items' && (
        <div className="comparison-section">
          {(!line_item_comparisons || line_item_comparisons.length === 0) ? (
            <p style={{ color: 'var(--text-secondary)' }}>No line items detected by either method.</p>
          ) : (
            <div className="comparison-table-wrapper">
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Row #</th>
                    <th>LLM Extracted Item</th>
                    <th>Non-LLM Extracted Item</th>
                    <th>Alignment</th>
                    <th>Analysis Details</th>
                  </tr>
                </thead>
                <tbody>
                  {line_item_comparisons.map((row) => (
                    <tr key={row.index}>
                      <td style={{ fontWeight: 'bold', color: '#94a3b8' }}>#{row.index}</td>
                      <td>
                        {row.llm_item ? (
                          <div>
                            <div style={{ fontWeight: 600, color: '#f8fafc' }}>{row.llm_item.description}</div>
                            <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                              Qty: {row.llm_item.quantity ?? '—'} &bull; Unit: {row.llm_item.unit_price ?? '—'} &bull; Total: {row.llm_item.line_total ?? '—'}
                            </div>
                          </div>
                        ) : (
                          <em style={{ color: '#64748b' }}>Not extracted by LLM</em>
                        )}
                      </td>
                      <td>
                        {row.non_llm_item ? (
                          <div>
                            <div style={{ fontWeight: 600, color: '#f8fafc' }}>{row.non_llm_item.description}</div>
                            <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                              Qty: {row.non_llm_item.quantity ?? '—'} &bull; Unit: {row.non_llm_item.unit_price ?? '—'} &bull; Total: {row.non_llm_item.line_total ?? '—'}
                            </div>
                          </div>
                        ) : (
                          <em style={{ color: '#64748b' }}>Not extracted by Non-LLM</em>
                        )}
                      </td>
                      <td>
                        <span className={`match-badge ${row.match_status === 'EXACT_MATCH' ? 'exact' : (row.match_status.includes('MISMATCH') ? 'mismatch' : 'missing')}`}>
                          {row.match_status === 'EXACT_MATCH' ? '✓ Exact Match' : row.match_status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                        {row.difference_note}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Financial Validation Comparison */}
      {activeTab === 'financial' && (
        <div className="comparison-section">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
            {/* LLM Financial Card */}
            <div style={{ background: 'rgba(3, 7, 18, 0.4)', padding: '1.5rem', borderRadius: '16px', border: '1px solid var(--border-color)' }}>
              <h4 style={{ margin: '0 0 1rem 0', color: '#818cf8', fontFamily: 'Outfit, sans-serif' }}>
                LLM Extraction Arithmetic Check
              </h4>
              <div className="method-stat-row">
                <span className="stat-label">Subtotal:</span>
                <span className="stat-val">{formatCurrency(llm_result.financial_validation?.subtotal, llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Tax:</span>
                <span className="stat-val">{formatCurrency(llm_result.financial_validation?.tax_amount, llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Total Amount:</span>
                <span className="stat-val">{formatCurrency(llm_result.financial_validation?.total_amount, llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Math Consistency:</span>
                <span className={`stat-val ${llm_result.financial_validation?.total_consistent ? 'success' : ''}`}>
                  {llm_result.financial_validation?.total_consistent ? '✓ Subtotal + Tax = Total' : 'Discrepancy detected'}
                </span>
              </div>
            </div>

            {/* Non-LLM Financial Card */}
            <div style={{ background: 'rgba(3, 7, 18, 0.4)', padding: '1.5rem', borderRadius: '16px', border: '1px solid var(--border-color)' }}>
              <h4 style={{ margin: '0 0 1rem 0', color: '#c084fc', fontFamily: 'Outfit, sans-serif' }}>
                Non-LLM Extraction Arithmetic Check
              </h4>
              <div className="method-stat-row">
                <span className="stat-label">Subtotal:</span>
                <span className="stat-val">{formatCurrency(non_llm_result.financial_validation?.subtotal, non_llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Tax:</span>
                <span className="stat-val">{formatCurrency(non_llm_result.financial_validation?.tax_amount, non_llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Total Amount:</span>
                <span className="stat-val">{formatCurrency(non_llm_result.financial_validation?.total_amount, non_llm_result.extracted_data?.currency)}</span>
              </div>
              <div className="method-stat-row">
                <span className="stat-label">Math Consistency:</span>
                <span className={`stat-val ${non_llm_result.financial_validation?.total_consistent ? 'success' : ''}`}>
                  {non_llm_result.financial_validation?.total_consistent ? '✓ Subtotal + Tax = Total' : 'Discrepancy detected'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary Bullet Points */}
      {summary_notes && summary_notes.length > 0 && (
        <div className="notes-box">
          <h4>Comparison Summary & Verification Findings:</h4>
          <ul>
            {summary_notes.map((note, idx) => (
              <li key={idx}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Bar */}
      <div className="comparison-actions">
        <button className="btn-back" onClick={onBack}>
          ← Back to Upload
        </button>
        <button
          className="btn-proceed-nonllm"
          onClick={() => onProceedWithMode('non_llm')}
          disabled={!non_llm_result.success}
          title={!non_llm_result.success ? 'Non-LLM extraction failed on this document' : 'Proceed with Non-LLM extraction into pipeline'}
        >
          Proceed with Non-LLM Extraction
        </button>
        <button
          className="btn-proceed-llm"
          onClick={() => onProceedWithMode('llm')}
          disabled={!llm_result.success}
          title="Proceed with production LLM extraction into pipeline"
        >
          Proceed with LLM Extraction (Recommended)
        </button>
      </div>
    </div>
  );
};

export default ExtractionComparison;
