import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';

import { cssVar } from '../lib/theme';

export default function MicroLesson({ lessonData, studentCode, cognitiveState, onStartQuiz }) {
  const mermaidRef = useRef(null);
  const [mermaidError, setMermaidError] = useState(false);

  useEffect(() => {
    if (lessonData && lessonData.mermaidDiagram && mermaidRef.current) {
      // Mermaid renders its own SVG with its own palette, so the built-in
      // 'dark' theme was the last dark surface left in this UI. 'base' plus
      // themeVariables is the only way to hand it our tokens - and it needs
      // resolved colours, because var() does not work in SVG attributes.
      mermaid.initialize({
        startOnLoad: false,
        theme: 'base',
        securityLevel: 'loose',
        fontFamily: cssVar('--cg-font'),
        themeVariables: {
          background: cssVar('--cg-card'),
          primaryColor: cssVar('--cg-accent-soft'),
          primaryTextColor: cssVar('--cg-ink'),
          primaryBorderColor: cssVar('--cg-accent'),
          secondaryColor: cssVar('--cg-page-alt'),
          tertiaryColor: cssVar('--cg-card-alt'),
          lineColor: cssVar('--cg-muted'),
          textColor: cssVar('--cg-body'),
          mainBkg: cssVar('--cg-accent-soft'),
          nodeBorder: cssVar('--cg-accent'),
          clusterBkg: cssVar('--cg-card-alt'),
          clusterBorder: cssVar('--cg-border'),
        },
      });

      // 🛠️ Deep Sanitize the Mermaid String from AI
      const cleanMermaid = lessonData.mermaidDiagram
        .replace(/```mermaid\s*/gi, '') // Remove opening markdown
        .replace(/```\s*/g, '')         // Remove closing markdown
        .replace(/\\n/g, '\n')          // Fix literal \n to actual line breaks
        .trim();

      const renderDiagram = async () => {
        try {
          setMermaidError(false);
          mermaidRef.current.removeAttribute('data-processed');
          mermaidRef.current.innerHTML = cleanMermaid; // Inject clean text
          await mermaid.run({ nodes: [mermaidRef.current] });
        } catch (error) {
          console.error("Mermaid Render Error Caught:", error);
          setMermaidError(true);
        }
      };

      // Slight delay to ensure DOM is ready
      setTimeout(renderDiagram, 150);
    }
  }, [lessonData]);

  // 🧠 Reframe Cognitive State into positive growth-mindset message
  const getGrowthBadge = () => {
    switch (cognitiveState) {
      case "High Cognitive Load":
        return { label: "Deep Logic Construction Zone 🧠", color: "var(--cg-warn)", bg: "rgb(var(--cg-rgb-warn) / 0.15)" };
      case "Needs Simple Basics":
        return { label: "Concept Strengthening Zone 🏗️", color: "var(--cg-accent)", bg: "rgb(var(--cg-rgb-accent) / 0.15)" };
      default:
        return { label: "Active Mastery Track ⚡", color: "var(--cg-ok)", bg: "rgb(var(--cg-rgb-ok) / 0.15)" };
    }
  };

  const badgeInfo = getGrowthBadge();

  return (
    <div className="fadeIn MicroLesson">
      <div className="cg-card cg-glass-panel" style={{ padding: '0', overflow: 'hidden' }}>
        
        {/* Header with Growth-Mindset Badge */}
        <div style={{ background: 'linear-gradient(90deg, rgb(var(--cg-rgb-card)) 0%, rgb(var(--cg-rgb-card)) 100%)', padding: '25px 40px', borderBottom: '1px solid var(--cg-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
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
            <h4 className="cg-title-content" style={{ color: 'var(--cg-danger)', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>🎯</span> The Core Issue
            </h4>
            <p className="cg-text-muted" style={{ fontSize: '1.05rem', lineHeight: '1.7' }}>{lessonData.issue}</p>
          </div>

          <div className="cg-lesson-section cg-hover-lift">
            <h4 className="cg-title-content" style={{ color: 'var(--cg-accent-bright)', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>💡</span> Concept Breakdown
            </h4>
            <p className="cg-text-muted" style={{ fontSize: '1.05rem', lineHeight: '1.7' }}>{lessonData.explanation}</p>
          </div>

          {/* ⚖️ TIME-TRAVEL CODE DIFF VIEW (Before vs After) */}
          <div className="cg-lesson-section cg-hover-lift">
            <h4 className="cg-title-content" style={{ color: 'var(--cg-accent)', display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
              <span>⚖️</span> Comparative Code Analysis (Before vs After)
            </h4>
            
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
              {/* Problematic Student Code */}
              <div style={{ background: 'var(--cg-page)', borderRadius: '12px', border: '1px solid rgb(var(--cg-rgb-danger) / 0.3)', overflow: 'hidden' }}>
                <div style={{ background: 'var(--cg-danger-soft)', padding: '10px 16px', borderBottom: '1px solid rgb(var(--cg-rgb-danger) / 0.2)', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--cg-danger)', fontSize: '0.85rem', fontWeight: 'bold' }}>
                  {/* Code Coach stores only a hash of the code around a
                      diagnostic, never the source, so a lesson opened from a
                      remediation trigger has no student code behind it. Say
                      so rather than passing a canned example off as theirs. */}
                  <span>✕</span> {lessonData.exampleIsGeneric
                    ? 'Problematic Logic (Typical Example)'
                    : 'Problematic Logic (Active Code)'}
                </div>
                <pre style={{ margin: 0, padding: '16px', color: 'var(--cg-danger)', fontFamily: 'var(--cg-font-mono)', fontSize: '0.9rem', overflowX: 'auto', lineHeight: '1.5' }}>
                  <code>{studentCode ? studentCode.replace(/\\n/g, '\n') : "int[] arr = new int[5];\narr[5] = 10; // Index 5 is out of bounds!"}</code>
                </pre>
              </div>

              {/* Remediated Correct Code */}
              <div style={{ background: 'var(--cg-page)', borderRadius: '12px', border: '1px solid rgb(var(--cg-rgb-ok) / 0.3)', overflow: 'hidden' }}>
                <div style={{ background: 'var(--cg-ok-soft)', padding: '10px 16px', borderBottom: '1px solid rgb(var(--cg-rgb-ok) / 0.2)', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--cg-ok)', fontSize: '0.85rem', fontWeight: 'bold' }}>
                  <span>✓</span> Remediated Implementation
                </div>
                <pre style={{ margin: 0, padding: '16px', color: 'var(--cg-ok)', fontFamily: 'var(--cg-font-mono)', fontSize: '0.9rem', overflowX: 'auto', lineHeight: '1.5' }}>
                  <code>{lessonData.exampleCode ? lessonData.exampleCode.replace(/\\n/g, '\n') : "int[] arr = new int[5];\narr[4] = 10; // Valid indices: 0 to 4"}</code>
                </pre>
              </div>
            </div>
          </div>

          {/* DYNAMIC AI GENERATED DIAGRAM */}
          {lessonData.mermaidDiagram && (
            <div className="cg-lesson-section cg-hover-lift">
              <h4 className="cg-title-content" style={{ color: 'var(--cg-ok)', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span>📊</span> Visual Concept Model
              </h4>
              
              {/* 🛠️ Fallback UI if AI sends broken Mermaid syntax */}
              {mermaidError ? (
                <div style={{ background: 'var(--cg-danger-soft)', border: '1px dashed rgb(var(--cg-rgb-danger) / 0.4)', borderRadius: '12px', padding: '20px', textAlign: 'center', marginTop: '15px' }}>
                  <span style={{ fontSize: '2rem', display: 'block', marginBottom: '10px' }}>🧩</span>
                  <h5 style={{ color: 'var(--cg-danger)', margin: '0 0 5px 0', fontSize: '1rem' }}>Diagram Generation Skipped</h5>
                  <p style={{ color: 'var(--cg-muted)', margin: 0, fontSize: '0.85rem' }}>The AI generated an overly complex structure that couldn't be rendered visually. Please rely on the code analysis above.</p>
                </div>
              ) : (
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
                  {/* Content is injected via JS ref above */}
                </div>
              )}
            </div>
          )}

          {(lessonData.videoUrl || lessonData.referenceLink) && (
            <div className="cg-lesson-section cg-glass-inner" style={{ padding: '25px' }}>
              <h4 className="cg-title-content" style={{ color: 'var(--cg-ink)', marginBottom: '20px' }}>📚 Recommended Resources</h4>
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
              <h4 className="cg-title-content" style={{ fontSize: '1.1rem', color: 'var(--cg-warn)', margin: 0 }}>Code Guru Pro Tip</h4>
            </div>
            <p style={{ margin: 0, fontStyle: 'italic', fontSize: '1rem', color: 'var(--cg-warn)', lineHeight: '1.6' }}>"{lessonData.hint}"</p>
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