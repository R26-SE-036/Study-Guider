import React from 'react';

const LEVEL_STYLES = {
  high: { label: 'High struggle', color: 'var(--cg-danger)', bg: 'rgb(var(--cg-rgb-danger) / 0.12)' },
  medium: { label: 'Medium struggle', color: 'var(--cg-warn)', bg: 'rgb(var(--cg-rgb-warn) / 0.12)' },
  low: { label: 'Low struggle', color: 'var(--cg-accent)', bg: 'rgb(var(--cg-rgb-accent) / 0.12)' },
};

/**
 * One remediation trigger raised by Code Coach.
 *
 * Everything shown here is real: the concept, the error type, how many times
 * it has happened, and Code Coach's own rationale for raising it. The card
 * used to take a single hardcoded `errorType` string.
 */
export default function TriggerCard({ trigger, loading, onGenerateLesson }) {
  const level = LEVEL_STYLES[trigger.struggle_level] || LEVEL_STYLES.low;
  const concept = (trigger.concept_tag || '').replace(/_/g, ' ');

  return (
    <div
      className="cg-card TriggerCard fadeIn cg-glass-panel"
      style={{ padding: '40px', position: 'relative', overflow: 'hidden', marginBottom: '24px' }}
    >
      <div
        className="cg-glow-bg"
        style={{
          background: 'radial-gradient(circle, rgb(var(--cg-rgb-danger) / 0.13) 0%, transparent 70%)',
          position: 'absolute',
          top: '-50%',
          left: '-50%',
          width: '200%',
          height: '200%',
          zIndex: 0,
          pointerEvents: 'none',
        }}
      ></div>

      <div style={{ position: 'relative', zIndex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
          <span
            style={{
              padding: '5px 12px',
              borderRadius: '999px',
              background: level.bg,
              color: level.color,
              fontSize: '0.75rem',
              fontWeight: 700,
              letterSpacing: '0.5px',
              textTransform: 'uppercase',
            }}
          >
            {level.label}
          </span>

          {typeof trigger.repeat_count === 'number' && (
            <span className="cg-text-muted" style={{ fontSize: '0.85rem' }}>
              seen {trigger.repeat_count}×
              {typeof trigger.active_count === 'number' && trigger.active_count > 0 &&
                ` · ${trigger.active_count} still unfixed`}
            </span>
          )}

          {trigger.hint_dependency_level && trigger.hint_dependency_level !== 'low' && (
            <span className="cg-text-muted" style={{ fontSize: '0.85rem' }}>
              · {trigger.hint_dependency_level} hint reliance
            </span>
          )}
        </div>

        <h2 className="cg-title-section" style={{ fontSize: '1.9rem', marginBottom: '10px', textTransform: 'capitalize' }}>
          <span className="cg-text-gradient-danger">{concept}</span>
        </h2>

        <code
          style={{
            display: 'inline-block',
            fontSize: '0.8rem',
            color: 'var(--cg-muted)',
            background: 'rgb(var(--cg-rgb-ink) / 0.072)',
            padding: '4px 10px',
            borderRadius: '6px',
            marginBottom: '18px',
            fontFamily: 'Fira Code, monospace',
          }}
        >
          {trigger.error_type}
        </code>

        {/* Code Coach's own explanation of why this was raised. */}
        <p className="cg-text-muted" style={{ fontSize: '1rem', lineHeight: 1.65, marginBottom: '24px', maxWidth: '680px' }}>
          {trigger.rationale}
        </p>

        {trigger.lesson && (
          <div
            style={{
              padding: '16px 18px',
              borderRadius: '12px',
              background: 'rgb(var(--cg-rgb-card) / 0.45)',
              border: '1px solid rgb(var(--cg-rgb-ink) / 0.072)',
              marginBottom: '28px',
            }}
          >
            <div style={{ fontSize: '0.75rem', color: 'var(--cg-muted)', fontWeight: 700, letterSpacing: '1px', marginBottom: '6px' }}>
              RECOMMENDED
            </div>
            <div style={{ color: 'var(--cg-body)', fontWeight: 600, marginBottom: '4px' }}>
              {trigger.lesson.title}
            </div>
            <div className="cg-text-muted" style={{ fontSize: '0.85rem' }}>
              ~{trigger.lesson.estimated_duration_minutes} min
              {trigger.quiz && ` · then a ${trigger.quiz.question_count}-question check (pass at ${trigger.quiz.passing_score_percent}%)`}
            </div>
          </div>
        )}

        <button
          onClick={onGenerateLesson}
          disabled={loading}
          className="cg-btn cg-btn-premium-success"
          style={{ padding: '15px 34px', fontSize: '1.05rem' }}
        >
          {loading ? (
            <><span className="spinner">⏳</span> Building AI Context...</>
          ) : (
            <>Start Interactive Lesson <span style={{ marginLeft: '8px' }}>🚀</span></>
          )}
        </button>
      </div>
    </div>
  );
}
