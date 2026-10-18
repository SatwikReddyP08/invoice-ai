import React, { useState } from 'react';
import './App.css';
import UploadInvoice from './components/UploadInvoice';
import ReviewDesk from './components/ReviewDesk';
import InvoiceResults from './components/InvoiceResults';

function App() {
  const [activeTab, setActiveTab] = useState('process'); // 'process' | 'review_desk'
  const [selectedInvoice, setSelectedInvoice] = useState(null);

  const handleSelectInvoiceFromDesk = (invoice) => {
    setSelectedInvoice(invoice);
  };

  const handleBackToDesk = () => {
    setSelectedInvoice(null);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1 className="app-title">InVoice AI</h1>
        <p className="app-subtitle">Fixed Multi-Stage AI Pipeline & Financial Intelligence</p>

        {/* Global Navigation Bar */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '1rem',
          marginTop: '2rem'
        }}>
          <button
            onClick={() => {
              setActiveTab('process');
              setSelectedInvoice(null);
            }}
            style={{
              background: activeTab === 'process' && !selectedInvoice ? 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)' : 'rgba(255, 255, 255, 0.05)',
              color: activeTab === 'process' && !selectedInvoice ? '#ffffff' : 'var(--text-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '0.65rem 1.4rem',
              fontWeight: 600,
              fontSize: '0.95rem',
              cursor: 'pointer',
              boxShadow: activeTab === 'process' && !selectedInvoice ? '0 4px 15px rgba(99, 102, 241, 0.35)' : 'none',
              transition: 'all 0.2s ease'
            }}
          >
            📄 Upload & Process
          </button>
          <button
            onClick={() => {
              setActiveTab('review_desk');
              setSelectedInvoice(null);
            }}
            style={{
              background: activeTab === 'review_desk' || selectedInvoice ? 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)' : 'rgba(255, 255, 255, 0.05)',
              color: activeTab === 'review_desk' || selectedInvoice ? '#ffffff' : 'var(--text-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '0.65rem 1.4rem',
              fontWeight: 600,
              fontSize: '0.95rem',
              cursor: 'pointer',
              boxShadow: activeTab === 'review_desk' || selectedInvoice ? '0 4px 15px rgba(99, 102, 241, 0.35)' : 'none',
              transition: 'all 0.2s ease'
            }}
          >
            🛡️ Invoice Review Desk
          </button>
        </div>
      </header>
      
      <main style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
        {selectedInvoice ? (
          <div style={{ width: '100%', maxWidth: '950px' }}>
            <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'flex-start' }}>
              <button
                onClick={handleBackToDesk}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  color: '#e2e8f0',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  padding: '0.5rem 1rem',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                ← Back to Review Desk Queue
              </button>
            </div>
            <InvoiceResults
              data={selectedInvoice}
              onReset={handleBackToDesk}
            />
          </div>
        ) : activeTab === 'process' ? (
          <UploadInvoice />
        ) : (
          <ReviewDesk onSelectInvoice={handleSelectInvoiceFromDesk} />
        )}
      </main>
    </div>
  );
}

export default App;
