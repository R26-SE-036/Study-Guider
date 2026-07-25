import React from 'react';

export default function TriggerCard({ errorType, loading, onGenerateLesson }) {
  return (
    <div className="cg-card TriggerCard fadeIn cg-glass-panel" style={{ textAlign: 'center', padding: '60px 40px', position: 'relative', overflow: 'hidden' }}>
      
      {/* Subtle background glow */}
      <div className="cg-glow-bg" style={{ background: 'radial-gradient(circle, rgba(248, 113, 113, 0.15) 0%, transparent 70%)', position: 'absolute', top: '-50%', left: '-50%', width: '200%', height: '200%', zIndex: 0, pointerEvents: 'none' }}></div>

      <div style={{ position: 'relative', zIndex: 1 }}>
        <div className="cg-animate-bounce-slow" style={{ fontSize: '4rem', marginBottom: '20px', filter: 'drop-shadow(0 0 15px rgba(245, 158, 11, 0.4))' }}>⚠️</div>
        
        <h2 className="cg-title-section" style={{ fontSize: '2.2rem', marginBottom: '15px' }}>
          <span className="cg-text-gradient-danger">Struggle Pattern Detected</span>
        </h2>
        
        <p className="cg-text-muted" style={{ fontSize: '1.1rem', marginBottom: '40px', maxWidth: '650px', margin: '0 auto 40px', lineHeight: '1.6' }}>
          We noticed repeated logical issues regarding <strong style={{color: '#F8FAFC', padding: '4px 12px', background: 'rgba(255,255,255,0.1)', borderRadius: '6px', marginLeft: '6px', letterSpacing: '0.5px'}}>{errorType}</strong> in your active coding session. 
          Let's take a quick micro-lesson to master this concept.
        </p>
        
        <button onClick={onGenerateLesson} disabled={loading} className="cg-btn cg-btn-premium-success" style={{ padding: '16px 36px', fontSize: '1.1rem' }}>
          {loading ? (
            <><span className="spinner">⏳</span> Building AI Context...</>
          ) : (
            <>Start Interactive Lesson <span style={{marginLeft: '8px'}}>🚀</span></>
          )}
        </button>
      </div>
    </div>
  );
}