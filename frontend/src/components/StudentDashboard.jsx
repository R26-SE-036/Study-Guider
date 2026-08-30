import React, { useState, useEffect } from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip as RechartsTooltip
} from 'recharts';

import api from '../lib/api';

/**
 * The student's analytics view, across the whole platform.
 *
 * This used to read only Study Guider's own Neo4j quiz history, which meant a
 * student with weeks of real activity - diagnostics, struggles, remediation -
 * opened it and saw "No Data Points Found" purely because they had not taken a
 * quiz *here* yet. Worse, the empty state told them to check Neo4j, which was
 * connected and fine.
 *
 * It now leads with Code Coach's cross-component overview (the errors they
 * actually made, which concepts are at risk, what they have worked through) and
 * keeps the Neo4j quiz history as one section rather than the whole page.
 *
 * No studentId prop: the backend reads the student from the bearer token.
 */

const STRUGGLE_COLOURS = { high: '#F87171', medium: '#FBBF24', low: '#60A5FA' };
const MASTERY_COLOURS = { strong: '#34D399', developing: '#FBBF24', at_risk: '#F87171' };

function StatCard({ label, value, colour, hint }) {
  return (
    <div className="cg-stat-card cg-glass-inner">
      <span className="cg-text-muted" style={{ fontSize: '0.8rem', letterSpacing: '1px', textTransform: 'uppercase' }}>
        {label}
      </span>
      <h1 style={{ margin: '6px 0 0 0', color: colour, fontSize: '2.2rem', textShadow: `0 0 20px ${colour}44` }}>
        {value}
      </h1>
      {hint && <span className="cg-text-muted" style={{ fontSize: '0.78rem' }}>{hint}</span>}
    </div>
  );
}

export default function StudentDashboard({ cognitiveState, onBack }) {
  const [overview, setOverview] = useState(null);
  const [progressData, setProgressData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [overviewError, setOverviewError] = useState('');

  useEffect(() => {
    // Two independent sources: Code Coach for the platform-wide picture, Neo4j
    // for this service's own quiz history. Fetched together, but one failing
    // must not blank the other - they answer different questions.
    Promise.allSettled([
      api.get('/api/dashboard/overview'),
      api.get('/api/progress/me'),
    ]).then(([overviewRes, progressRes]) => {
      if (overviewRes.status === 'fulfilled') {
        setOverview(overviewRes.value.data);
      } else {
        const status = overviewRes.reason?.response?.status;
        if (status !== 401) {
          setOverviewError(
            overviewRes.reason?.response?.data?.detail ||
              'Could not reach Code Coach for your platform activity.',
          );
        }
      }

      if (progressRes.status === 'fulfilled' && progressRes.value.data?.success) {
        setProgressData(progressRes.value.data.data || []);
      } else {
        setProgressData([]);
      }

      setLoading(false);
    });
  }, []);

  const counts = overview?.counts || {};
  const mastery = overview?.mastery || {};
  const conceptTrends = overview?.concept_trends || [];
  const timeline = overview?.recent_timeline || [];

  // Quiz history (Neo4j) - this service's own contribution to the picture.
  const totalAssessments = progressData.length;
  const masteredCount = progressData.filter((item) => item.status === 'MASTERED').length;
  const avgAccuracy = totalAssessments > 0
    ? Math.round((progressData.reduce((acc, curr) => acc + (curr.score / curr.total), 0) / totalAssessments) * 100)
    : 0;

  // The radar now plots Code Coach's per-concept mastery when it has any,
  // falling back to quiz percentages so the chart still works for a student
  // whose only activity has been here.
  const radarData = conceptTrends.length > 0
    ? conceptTrends.map((t) => ({
        subject: (t.concept_tag || '').replace(/_/g, ' '),
        A: Math.round((t.mastery_score ?? 0) * 100),
        fullMark: 100,
      }))
    : Object.values(progressData.reduce((acc, curr) => {
        if (!acc[curr.concept]) acc[curr.concept] = { concept: curr.concept, totalScore: 0, maxPossible: 0 };
        acc[curr.concept].totalScore += curr.score;
        acc[curr.concept].maxPossible += curr.total;
        return acc;
      }, {})).map((stat) => ({
        subject: stat.concept.replace(/_/g, ' '),
        A: Math.round((stat.totalScore / stat.maxPossible) * 100),
        fullMark: 100,
      }));

  const hasAnything = conceptTrends.length > 0 || timeline.length > 0 || totalAssessments > 0;

  return (
    <div className="cg-card fadeIn cg-glass-panel" style={{ padding: '50px' }}>

      <div className="cg-flex-between" style={{ marginBottom: '40px', paddingBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ width: '50px', height: '50px', background: 'linear-gradient(135deg, #3B82F6, #8B5CF6)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', boxShadow: '0 10px 20px rgba(59, 130, 246, 0.3)' }}>📊</div>
          <div>
            <h2 className="cg-title-section" style={{ fontSize: '2rem', margin: 0 }}>Learning Analytics</h2>
            <p className="cg-text-muted" style={{ margin: '5px 0 0 0', fontSize: '1rem' }}>
              Your activity across Code Coach, Study Guider, PairPath and Gamification
            </p>
          </div>
        </div>
        <button onClick={onBack} className="cg-btn cg-btn-outline">← Back</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <div className="spinner" style={{ fontSize: '3rem', display: 'inline-block', marginBottom: '20px' }}>📈</div>
          <h3 className="cg-title-section cg-text-gradient-primary">Gathering your activity…</h3>
        </div>
      ) : !hasAnything ? (
        <div style={{ textAlign: 'center', padding: '70px 20px' }}>
          <div style={{ fontSize: '3.5rem', marginBottom: '18px' }}>🌱</div>
          <h3 className="cg-title-content" style={{ color: '#E2E8F0', fontSize: '1.5rem' }}>Nothing to show yet</h3>
          {/* The old copy here blamed Neo4j, which was almost never the cause -
              an empty history looks identical to a broken database unless you
              say which one it is. */}
          <p className="cg-text-muted" style={{ maxWidth: '520px', margin: '12px auto 0', lineHeight: 1.65 }}>
            Code Coach has not recorded any activity for you yet. Write some Java in the VS Code
            extension and your errors, struggles and progress will appear here.
          </p>
          {overviewError && (
            <p style={{ color: '#FCA5A5', fontSize: '0.85rem', marginTop: '18px' }}>{overviewError}</p>
          )}
        </div>
      ) : (
        <div>
          {overviewError && (
            <div style={{ padding: '12px 16px', borderRadius: '10px', background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)', color: '#FCD34D', marginBottom: '28px', fontSize: '0.88rem' }}>
              {overviewError} Showing your Study Guider quiz history only.
            </div>
          )}

          {/* ── Platform-wide counts (Code Coach) ── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px', marginBottom: '36px' }}>
            <StatCard
              label="Errors Found"
              value={counts.total_diagnostics ?? 0}
              colour="#60A5FA"
              hint={`${counts.active_diagnostics ?? 0} still unfixed`}
            />
            <StatCard
              label="Concepts At Risk"
              value={mastery.at_risk_count ?? 0}
              colour={MASTERY_COLOURS.at_risk}
              hint={`${mastery.strong_count ?? 0} strong · ${mastery.developing_count ?? 0} developing`}
            />
            <StatCard
              label="Remediation"
              value={counts.completed_remediation_triggers ?? 0}
              colour={MASTERY_COLOURS.strong}
              hint={`${counts.active_remediation_triggers ?? 0} still open`}
            />
            <StatCard
              label="Quiz Accuracy"
              value={`${avgAccuracy}%`}
              colour={avgAccuracy >= 50 ? '#34D399' : '#FBBF24'}
              hint={`${totalAssessments} assessment(s), ${masteredCount} mastered`}
            />
            <StatCard
              label="Cognitive State"
              value={String(cognitiveState || '—').split(' ')[0]}
              colour="#F472B6"
              hint={cognitiveState || 'not measured'}
            />
          </div>

          {/* ── Per-concept trends (Code Coach) ── */}
          {conceptTrends.length > 0 && (
            <div className="cg-glass-inner" style={{ padding: '28px', borderRadius: '16px', marginBottom: '36px' }}>
              <h3 className="cg-title-content" style={{ marginBottom: '22px', fontSize: '1.3rem' }}>
                🎯 Concept Breakdown
              </h3>
              <div className="cg-flex-col" style={{ gap: '12px' }}>
                {conceptTrends.map((t) => (
                  <div key={t.concept_tag} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', padding: '14px 18px', borderRadius: '12px', background: 'rgba(15,23,42,0.45)', border: '1px solid rgba(255,255,255,0.06)', flexWrap: 'wrap' }}>
                    <div style={{ minWidth: '180px' }}>
                      <div style={{ color: '#F8FAFC', fontWeight: 600, textTransform: 'capitalize' }}>
                        {(t.concept_tag || '').replace(/_/g, ' ')}
                      </div>
                      <div className="cg-text-muted" style={{ fontSize: '0.8rem' }}>
                        seen {t.repeat_count ?? 0}× · {t.active_count ?? 0} unfixed
                      </div>
                    </div>
                    <span style={{ padding: '4px 12px', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: STRUGGLE_COLOURS[t.struggle_level] || '#94A3B8', background: `${STRUGGLE_COLOURS[t.struggle_level] || '#94A3B8'}22` }}>
                      {t.struggle_level || 'unknown'} struggle
                    </span>
                    <span style={{ padding: '4px 12px', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: MASTERY_COLOURS[t.mastery_level] || '#94A3B8', background: `${MASTERY_COLOURS[t.mastery_level] || '#94A3B8'}22` }}>
                      {(t.mastery_level || 'unrated').replace(/_/g, ' ')}
                    </span>
                    {t.recommended_focus && (
                      <span className="cg-text-muted" style={{ fontSize: '0.8rem', flex: 1, minWidth: '160px' }}>
                        {t.recommended_focus}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Skill map ── */}
          {radarData.length > 0 && (
            <div className="cg-chart-container cg-glass-inner" style={{ padding: '30px', borderRadius: '16px', marginBottom: '36px', position: 'relative' }}>
              <h3 className="cg-title-content cg-text-gradient-primary" style={{ textAlign: 'center', marginBottom: '30px', fontSize: '1.5rem' }}>
                Cognitive Skill Map
              </h3>
              <ResponsiveContainer width="100%" height={320}>
                <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                  <defs>
                    <linearGradient id="colorUv" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.8} />
                      <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.3} />
                    </linearGradient>
                  </defs>
                  <PolarGrid stroke="rgba(255,255,255,0.12)" />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: '#94A3B8', fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#475569', fontSize: 10 }} />
                  <RechartsTooltip contentStyle={{ background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '10px' }} />
                  <Radar name="Mastery (%)" dataKey="A" stroke="#8B5CF6" strokeWidth={3} fill="url(#colorUv)" fillOpacity={0.6} />
                </RadarChart>
              </ResponsiveContainer>
              <p className="cg-text-muted" style={{ textAlign: 'center', fontSize: '0.8rem', marginTop: '4px' }}>
                {conceptTrends.length > 0 ? 'Mastery per concept, from Code Coach' : 'Quiz accuracy per concept'}
              </p>
            </div>
          )}

          {/* ── Activity timeline, spanning all components ── */}
          {timeline.length > 0 && (
            <div className="cg-glass-inner" style={{ padding: '28px', borderRadius: '16px', marginBottom: '36px' }}>
              <h3 className="cg-title-content" style={{ marginBottom: '22px', fontSize: '1.3rem' }}>
                🕒 Recent Activity
              </h3>
              <div className="cg-flex-col" style={{ gap: '10px' }}>
                {timeline.map((e) => (
                  <div key={e.event_id} style={{ display: 'flex', alignItems: 'flex-start', gap: '14px', padding: '12px 16px', borderRadius: '10px', background: 'rgba(15,23,42,0.4)' }}>
                    <span style={{ padding: '3px 9px', borderRadius: '6px', fontSize: '0.68rem', fontWeight: 700, textTransform: 'uppercase', color: '#93C5FD', background: 'rgba(96,165,250,0.15)', whiteSpace: 'nowrap' }}>
                      {(e.component || '').replace(/_/g, ' ')}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: '#E2E8F0', fontSize: '0.92rem' }}>{e.title || e.event_type}</div>
                      {e.summary && <div className="cg-text-muted" style={{ fontSize: '0.8rem' }}>{e.summary}</div>}
                    </div>
                    <span className="cg-text-muted" style={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {e.occurred_at ? new Date(e.occurred_at).toLocaleString() : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Study Guider's own quiz history (Neo4j) ── */}
          <div>
            <h3 className="cg-title-content" style={{ marginBottom: '22px', display: 'flex', alignItems: 'center', gap: '10px', fontSize: '1.3rem' }}>
              📝 Your Study Guider Quizzes
            </h3>
            {progressData.length === 0 ? (
              <p className="cg-text-muted" style={{ fontSize: '0.9rem' }}>
                No quizzes completed here yet. Work through a lesson and its quiz to build this up.
              </p>
            ) : (
              <div className="cg-flex-col" style={{ gap: '14px' }}>
                {progressData.map((item, index) => {
                  const pct = Math.round((item.score / item.total) * 100);
                  return (
                    <div key={index} className="cg-history-card" style={{ padding: '18px 22px', borderRadius: '12px', background: 'rgba(15,23,42,0.45)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <div className="cg-flex-between" style={{ flexWrap: 'wrap', gap: '10px' }}>
                        <h4 style={{ margin: 0, color: '#F8FAFC', fontFamily: 'Fira Code', fontSize: '1.05rem', textTransform: 'capitalize' }}>
                          {String(item.concept).replace(/_/g, ' ')}
                        </h4>
                        <span style={{ color: item.status === 'MASTERED' ? '#34D399' : '#FBBF24', fontWeight: 700, fontSize: '0.85rem' }}>
                          {item.status} · {item.score}/{item.total} ({pct}%)
                        </span>
                      </div>
                      {item.last_updated && (
                        <div className="cg-text-muted" style={{ fontSize: '0.76rem', marginTop: '6px' }}>
                          {new Date(item.last_updated).toLocaleString()}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
