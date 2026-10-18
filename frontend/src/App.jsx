import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import UploadInvoice from './components/UploadInvoice';
import ReviewDesk from './components/ReviewDesk';
import InvoiceResults from './components/InvoiceResults';

function App() {
  const [activeTab, setActiveTab] = useState('process'); // 'process' | 'review_desk'
  const [selectedInvoice, setSelectedInvoice] = useState(null);
  const [sourceView, setSourceView] = useState('upload'); // 'upload' | 'review_desk'
  const [reviewFilter, setReviewFilter] = useState('needs_attention');
  const [isLoadingInvoice, setIsLoadingInvoice] = useState(false);

  const selectedInvoiceRef = useRef(selectedInvoice);
  useEffect(() => {
    selectedInvoiceRef.current = selectedInvoice;
  }, [selectedInvoice]);

  // Synchronize navigation state with URL hash for seamless browser Back/Forward support
  useEffect(() => {
    const handleHashNavigation = async () => {
      const hash = window.location.hash;
      if (hash.startsWith('#invoice-')) {
        const id = hash.replace('#invoice-', '');
        const currentInv = selectedInvoiceRef.current;
        if (id && (!currentInv || currentInv.id !== parseInt(id, 10))) {
          setIsLoadingInvoice(true);
          try {
            const res = await fetch(`/api/v1/invoices/${id}`);
            if (res.ok) {
              const inv = await res.json();
              setSelectedInvoice(inv);
              setActiveTab('review_desk');
            } else {
              window.location.hash = '#review';
            }
          } catch {
            window.location.hash = '#review';
          } finally {
            setIsLoadingInvoice(false);
          }
        }
      } else if (hash === '#review') {
        setSelectedInvoice(null);
        setActiveTab('review_desk');
      } else if (hash === '#upload' || hash === '') {
        setSelectedInvoice(null);
        setActiveTab('process');
      }
    };

    handleHashNavigation();
    window.addEventListener('hashchange', handleHashNavigation);
    return () => window.removeEventListener('hashchange', handleHashNavigation);
  }, []);

  const handleSelectInvoiceFromDesk = (invoice) => {
    setSelectedInvoice(invoice);
    setSourceView('review_desk');
    window.location.hash = `#invoice-${invoice.id}`;
  };

  const handleInvoiceProcessed = (invoice) => {
    setSelectedInvoice(invoice);
    setSourceView('upload');
    window.location.hash = `#invoice-${invoice.id}`;
  };

  const handleBackToDesk = () => {
    setSelectedInvoice(null);
    setActiveTab('review_desk');
    window.location.hash = '#review';
  };

  const handleUploadNewInvoice = () => {
    setSelectedInvoice(null);
    setActiveTab('process');
    window.location.hash = '#upload';
  };

  const handleNavClick = (tab) => {
    setActiveTab(tab);
    setSelectedInvoice(null);
    window.location.hash = tab === 'review_desk' ? '#review' : '#upload';
  };

  const handleInvoiceUpdated = (updated) => {
    setSelectedInvoice(updated);
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
            onClick={() => handleNavClick('process')}
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
            onClick={() => handleNavClick('review_desk')}
            style={{
              background: activeTab === 'review_desk' && !selectedInvoice ? 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)' : 'rgba(255, 255, 255, 0.05)',
              color: activeTab === 'review_desk' && !selectedInvoice ? '#ffffff' : 'var(--text-secondary)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '0.65rem 1.4rem',
              fontWeight: 600,
              fontSize: '0.95rem',
              cursor: 'pointer',
              boxShadow: activeTab === 'review_desk' && !selectedInvoice ? '0 4px 15px rgba(99, 102, 241, 0.35)' : 'none',
              transition: 'all 0.2s ease'
            }}
          >
            🛡️ Invoice Review Desk
          </button>
        </div>
      </header>
      
      <main style={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
        {isLoadingInvoice ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
            <span className="spinner"></span> Loading invoice inspection...
          </div>
        ) : selectedInvoice ? (
          <div style={{ width: '100%', maxWidth: '950px' }}>
            <InvoiceResults
              data={selectedInvoice}
              sourceView={sourceView}
              onBackToDesk={handleBackToDesk}
              onUploadNew={handleUploadNewInvoice}
              onReset={handleUploadNewInvoice}
              onInvoiceUpdated={handleInvoiceUpdated}
            />
          </div>
        ) : activeTab === 'process' ? (
          <UploadInvoice onInvoiceProcessed={handleInvoiceProcessed} />
        ) : (
          <ReviewDesk 
            onSelectInvoice={handleSelectInvoiceFromDesk} 
            activeFilter={reviewFilter}
            onFilterChange={setReviewFilter}
          />
        )}
      </main>
    </div>
  );
}

export default App;
