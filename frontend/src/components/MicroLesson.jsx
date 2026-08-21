import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

export default function MicroLesson({ lessonData, studentCode, cognitiveState, onStartQuiz }) {
  const mermaidRef = useRef(null);

  useEffect(() => {
    if (lessonData && lessonData.mermaidDiagram && mermaidRef.current) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark', 
        securityLevel: 'loose',
      });

      setTimeout(() => {
        try {
          mermaidRef.current.removeAttribute('data-processed');
          mermaid.run({ nodes: [mermaidRef.current] });
        } catch (error) {
          console.error("Mermaid Render Error:", error);
        }
      }, 100);
    }
  }, [lessonData]);

  // 🧠 Reframe Cognitive State into positive growth-mindset message
  const getGrowthBadge = () => {
    switch (cognitiveState) {
      case "High Cognitive Load":
        return { label: "Deep Logic Construction Zone 🧠", color: "#F59E0B", bg: "rgba(245, 158, 11, 0.15)" };
      case "Needs Simple Basics":
        return { label: "Concept Strengthening Zone 🏗️", color: "#3B82F6", bg: "rgba(59, 130, 246, 0.15)" };
      default:
        return { label: "Active Mastery Track ⚡", color: "#10B981", bg: "rgba(16, 185, 129, 0.15)" };
    }
  };

  const badgeInfo = getGrowthBadge();

  return (
    <div className="fadeIn MicroLesson">
      <div className="cg-card cg-glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
        
        {/* Header with Growth-Mindset Badge */}
        <div style={{ background: 'linear-gradient(90deg, rgba(15, 23, 42, 1) 0%, rgba(30, 41, 59, 1) 100%)', padding: '25px 40px', borderBottom: '1px solid rgba(255,255,255,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <span style={{ fontSize: '1.8rem' }}>🧠</span>
            <h3 className="cg-title-content cg-text-gradient-primary" style={{ margin: 0, fontSize: '1.5rem', fontWeight: '700' }}>
              {lessonData.title || "Understanding Your Logic Error"}
            </h3>
          </div>
          <div style={{ 
            padding: '6px 14px', 
            borderRadius: '20px', 
            fontSize: '0.85rem', 
            fontWeight: '600', 
            backgroundColor: badgeInfo.bg, 
            color: badgeInfo.color,
            border: `1px solid ${badgeInfo.color}40`,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            {badgeInfo.label}
          </div>
        </div>

        <div style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '35px' }}>
          
          <div className="cg-lesson-section cg-hover-lift">
            <h4 className="cg-title-content" style={{ color: '#F87171', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>🎯</span> The Core Issue
            </h4>
            <p className="cg-text-muted" style={{ fontSize: '1.05rem', lineHeight: '1.7' }}>{lessonData.issue}</p>
          </div>

          <div className="cg-lesson-section cg-hover-lift">
            <h4 className="cg-title-content" style={{ color: '#A78BFA', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>💡</span> Concept Breakdown
            </h4>
            <p className="cg-text-muted" style={{ fontSize: '1.05rem', lineHeight: '1.7' }}>{lessonData.explanation}</p>
          </div>

          {/* ⚖️ TIME-TRAVEL CODE DIFF VIEW (Before vs After) */}
          <div className="cg-lesson-section cg-hover-lift">
            <h4 className="cg-title-content" style={{ color: '#60A5FA', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
              <span>⚖️</span> Comparative Code Analysis (Before vs After)
            </h4>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
              {/* Problematic Student Code */}
              <div style={{ background: '#0F172A', borderRadius: '12px', border: '1px solid rgba(239, 68, 68, 0.3)', overflow: 'hidden' }}>
                <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '10px 16px', borderBottom: '1px solid rgba(239, 68, 68, 0.2)', display: 'flex', alignItems: 'center', gap: '8px', color: '#F87171', fontSize: '0.85rem', fontWeight: 'bold' }}>
                  <span>✕</span> Problematic Logic (Active Code)
                </div>
                <pre style={{ margin: 0, padding: '16px', color: '#FCA5A5', fontFamily: 'Fira Code', fontSize: '0.9rem', overflowX: 'auto', lineHeight: '1.5' }}>
                  <code>{studentCode || "int[] arr = new int[5];\narr[5] = 10; // Index 5 is out of bounds!"}</code>
                </pre>
              </div>

              {/* Remediated Correct Code */}
              <div style={{ background: '#0F172A', borderRadius: '12px', border: '1px solid rgba(16, 185, 129, 0.3)', overflow: 'hidden' }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '10px 16px', borderBottom: '1px solid rgba(16, 185, 129, 0.2)', display: 'flex', alignItems: 'center', gap: '8px', color: '#34D399', fontSize: '0.85rem', fontWeight: 'bold' }}>
                  <span>✓</span> Remediated Implementation
                </div>
                <pre style={{ margin: 0, padding: '16px', color: '#6EE7B7', fontFamily: 'Fira Code', fontSize: '0.9rem', overflowX: 'auto', lineHeight: '1.5' }}>
                  <code>{lessonData.exampleCode || "int[] arr = new int[5];\narr[4] = 10; // Valid indices: 0 to 4"}</code>
                </pre>
              </div>
            </div>
          </div>

          {/* DYNAMIC AI GENERATED DIAGRAM */}
          {lessonData.mermaidDiagram && (
            <div className="cg-lesson-section cg-hover-lift">
              <h4 className="cg-title-content" style={{ color: '#34D399', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span>📊</span> Visual Concept Model
              </h4>
              <div 
                className="mermaid cg-glass-inner" 
                ref={mermaidRef} 
                style={{ 
                  padding: '25px', 
                  borderRadius: '12px', 
                  textAlign: 'center', 
                  marginTop: '15px', 
                  overflowX: 'auto' 
                }}
              >
                {lessonData.mermaidDiagram.replace(/\\n/g, '\n')}
              </div>
            </div>
          )}

          {(lessonData.videoUrl || lessonData.referenceLink) && (
            <div className="cg-lesson-section cg-glass-inner" style={{ padding: '25px' }}>
              <h4 className="cg-title-content" style={{ color: '#F8FAFC', marginBottom: '20px' }}>📚 Recommended Resources</h4>
              <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
                {lessonData.videoUrl && (
                  <a href={lessonData.videoUrl} target="_blank" rel="noopener noreferrer" className="cg-resource-link">
                    <span style={{ fontSize: '1.2rem' }}>▶️</span> Watch Video Tutorial
                  </a>
                )}
                {lessonData.referenceLink && (
                  <a href={lessonData.referenceLink} target="_blank" rel="noopener noreferrer" className="cg-resource-link">
                    <span style={{ fontSize: '1.2rem' }}>🌐</span> Read Documentation
                  </a>
                )}
              </div>
            </div>
          )}

          <div className="cg-pro-tip-box">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <span style={{ fontSize: '1.2rem' }}>⚡</span>
              <h4 className="cg-title-content" style={{ fontSize: '1.1rem', color: '#FBBF24', margin: 0 }}>Code Guru Pro Tip</h4>
            </div>
            <p style={{ margin: 0, fontStyle: 'italic', fontSize: '1rem', color: '#FDE68A', lineHeight: '1.6' }}>"{lessonData.hint}"</p>
          </div>
          
        </div>
      </div>

      <div style={{ marginTop: '35px', textAlign: 'right' }}>
        <button onClick={onStartQuiz} className="cg-btn cg-btn-premium-primary" style={{ padding: '14px 30px', fontSize: '1.05rem' }}>
          Verify Knowledge <span style={{marginLeft: '8px'}}>→</span>
        </button>
      </div>
    </div>
  );
}