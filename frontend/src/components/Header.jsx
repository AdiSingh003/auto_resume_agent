import React from 'react';
import { Bot, FileText, Sparkles } from 'lucide-react';

export default function Header({ onNewResume }) {
  return (
    <header style={{
      background: 'rgba(15, 23, 42, 0.8)',
      backdropFilter: 'blur(12px)',
      borderBottom: '1px solid var(--glass-border)',
      padding: '1rem 2rem',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ 
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            padding: '0.5rem',
            borderRadius: '8px',
            display: 'flex'
          }}>
            <Bot size={24} color="white" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.5rem', letterSpacing: '0.5px' }}>AutoResume Agent</h1>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Sparkles size={12} /> Powered by LangGraph & Groq
            </div>
          </div>
        </div>
        
        <nav style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn btn-outline" onClick={onNewResume}>
            <FileText size={18} /> New Resume
          </button>
        </nav>
      </div>
    </header>
  );
}
