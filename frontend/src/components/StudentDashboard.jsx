import React, { useState, useEffect } from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip as RechartsTooltip
} from 'recharts';

import api from '../lib/api';
import { useThemeColors } from '../lib/theme';

/* Recharts hands these straight to SVG presentation attributes, where var()
   does not resolve - they have to be real colour values. Declared at module
   scope so the hook's identity is stable across renders. */
const CHART_TOKENS = {
  accent: '--cg-accent',
  grid: '--cg-border',
  axis: '--cg-muted',
};

/**
 * The student's analytics view, across the whole platform.
 *
 * This used to read only Study Guider's own Neo4j quiz history, so a student
 * with weeks of real activity - diagnostics, struggles, remediation - opened it
 * and saw "No Data Points Found" purely because they had not taken a quiz
 * *here* yet. The empty state then told them to check Neo4j, which was
 * connected and fine.
 *
 * It now leads with Code Coach's cross-component overview and keeps the Neo4j
 * quiz history as one section rather than the whole page.
 *
 * Styling lives in App.css under "LEARNING ANALYTICS" rather than inline, so
 * this view picks up the same glass and hover language as the rest of the app.
 *
 * No studentId prop: the backend reads the student from the bearer token.
 */

const STRUGGLE = {
  high: { colour: 'var(--cg-danger)', label: 'High struggle', weight: 1 },
  medium: { colour: 'var(--cg-warn)', label: 'Medium struggle', weight: 0.6 },
  low: { colour: 'var(--cg-accent)', label: 'Low struggle', weight: 0.3 },
};
const MASTERY = {
  strong: 'var(--cg-ok)',
  developing: 'var(--cg-warn)',
  at_risk: 'var(--cg-danger)',
};

const titleCase = (s) => String(s || '').replace(/_/g, ' ');

function StatTile({ label, value, colour, hint }) {
  return (
    <div className="cg-stat-tile">
      <span className="cg-stat-label">{label}</span>
      <div className="cg-stat-value" style={{ color: colour, textShadow: `0 0 22px ${colour}44` }}>
        {value}
      </div>
      {hint && <span className="cg-stat-hint">{hint}</span>}
    </div>
  );
}

function ConceptRow({ trend }) {
  const struggle = STRUGGLE[trend.struggle_level] || { colour: 'var(--cg-muted)', label: 'Unrated', weight: 0.15 };
  const masteryColour = MASTERY[trend.mastery_level] || 'var(--cg-muted)';

  // The meter reads as "how much attention does this need". Mastery is the
  // better signal when Code Coach has rated the concept; until a quiz or game
  // result closes that loop it stays unrated, so struggle level stands in.
  const rated = trend.mastery_score != null && trend.mastery_level;
  const fill = rated
    ? Math.round(trend.mastery_score * 100)
    : Math.round(struggle.weight * 100);

  return (
    <div className="cg-concept-row">
      <div className="cg-concept-top">
        <span className="cg-concept-name">{titleCase(trend.concept_tag)}</span>
        <span style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <span className="cg-chip" style={{ color: struggle.colour, background: `${struggle.colour}22` }}>
            {struggle.label}
          </span>
          <span className="cg-chip" style={{ color: masteryColour, background: `${masteryColour}22` }}>
            {rated ? titleCase(trend.mastery_level) : 'Not yet rated'}
          </span>
        </span>
      </div>

      <div className="cg-meter">
        <div
          className="cg-meter-fill"
          style={{
            width: `${fill}%`,
            background: rated
              ? `linear-gradient(90deg, ${masteryColour}, ${masteryColour}aa)`
              : `linear-gradient(90deg, ${struggle.colour}, ${struggle.colour}aa)`,
          }}
        />
      </div>

      <div className="cg-concept-meta">
        <span>seen {trend.repeat_count ?? 0}× · {trend.active_count ?? 0} still unfixed</span>
        {trend.recommended_focus && <span>→ {titleCase(trend.recommended_focus)}</span>}
      </div>
    </div>
  );
}

export default function StudentDashboard({ cognitiveState, onBack }) {
  const chart = useThemeColors(CHART_TOKENS);
  const [overview, setOverview] = useState(null);
  const [progressData, setProgressData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [overviewError, setOverviewError] = useState('');

  useEffect(() => {
    // Two independent sources: Code Coach for the platform-wide picture, Neo4j
    // for this service's own quiz history. One failing must not blank the
    // other - they answer different questions.
    Promise.allSettled([
      api.get('/api/dashboard/overview'),
      api.get('/api/progress/me'),
    ]).then(([overviewRes, progressRes]) => {
      if (overviewRes.status === 'fulfilled') {
        setOverview(overviewRes.value.data);
      } else if (overviewRes.reason?.response?.status !== 401) {
        setOverviewError(
          overviewRes.reason?.response?.data?.detail ||
            'Could not reach Code Coach for your platform activity.',
        );
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

  const totalAssessments = progressData.length;
  const masteredCount = progressData.filter((i) => i.status === 'MASTERED').length;
  const avgAccuracy = totalAssessments > 0
    ? Math.round((progressData.reduce((a, c) => a + (c.score / c.total), 0) / totalAssessments) * 100)
    : 0;

  // The radar plots Code Coach mastery when it has any, falling back to quiz
  // accuracy so the chart still works for a student whose only activity is here.
  const radarData = conceptTrends.length > 0
    ? conceptTrends.map((t) => ({
        subject: titleCase(t.concept_tag),
        A: Math.round((t.mastery_score ?? 0) * 100),
        fullMark: 100,
      }))
    : Object.values(progressData.reduce((acc, c) => {
        if (!acc[c.concept]) acc[c.concept] = { concept: c.concept, score: 0, max: 0 };
        acc[c.concept].score += c.score;
        acc[c.concept].max += c.total;
        return acc;
      }, {})).map((s) => ({
        subject: titleCase(s.concept),
        A: Math.round((s.score / s.max) * 100),
        fullMark: 100,
      }));

  const hasAnything = conceptTrends.length > 0 || timeline.length > 0 || totalAssessments > 0;

  return (
    <div className="cg-card fadeIn cg-glass-panel" style={{ padding: '42px' }}>

      <div className="cg-analytics-head">
        <div style={{ display: 'flex', alignItems: 'center', gap: '18px' }}>
          <div className="cg-analytics-icon">📊</div>
          <div>
            <h2 className="cg-title-section" style={{ fontSize: '1.85rem', margin: 0 }}>Learning Analytics</h2>
            <p className="cg-text-muted" style={{ margin: '4px 0 0 0', fontSize: '0.92rem' }}>
              Your activity across Code Coach, Study Guider, PairPath and Gamification
            </p>
          </div>
        </div>
        <button onClick={onBack} className="cg-btn cg-btn-outline">← Back</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '70px 0' }}>
          <div className="spinner" style={{ fontSize: '2.6rem', display: 'inline-block', marginBottom: '16px' }}>📈</div>
          <h3 className="cg-title-section cg-text-gradient-primary" style={{ fontSize: '1.3rem' }}>
            Gathering your activity…
          </h3>
        </div>
      ) : !hasAnything ? (
        <div style={{ textAlign: 'center', padding: '64px 20px' }}>
          <div style={{ fontSize: '3.2rem', marginBottom: '14px' }}>🌱</div>
          <h3 className="cg-title-content" style={{ color: 'var(--cg-body)', fontSize: '1.4rem', margin: 0 }}>
            Nothing to show yet
          </h3>
          {/* The old copy blamed Neo4j, which was almost never the cause - an
              empty history looks identical to a broken database unless you say
              which one it is. */}
          <p className="cg-text-muted" style={{ maxWidth: '480px', margin: '12px auto 0', lineHeight: 1.65, fontSize: '0.92rem' }}>
            Code Coach has not recorded any activity for you yet. Write some Java in the VS Code
            extension and your errors, struggles and progress will appear here.
          </p>
          {overviewError && (
            <p style={{ color: 'var(--cg-danger)', fontSize: '0.82rem', marginTop: '16px' }}>{overviewError}</p>
          )}
        </div>
      ) : (
        <div>
          {overviewError && (
            <div className="cg-section" style={{ padding: '12px 16px', borderRadius: '12px', background: 'rgb(var(--cg-rgb-warn) / 0.1)', border: '1px solid rgb(var(--cg-rgb-warn) / 0.28)', color: 'var(--cg-warn)', fontSize: '0.86rem' }}>
              {overviewError} Showing your Study Guider quiz history only.
            </div>
          )}

          <div className="cg-section cg-stat-grid cg-stagger">
            <StatTile
              label="Errors Found" value={counts.total_diagnostics ?? 0} colour="var(--cg-accent)"
              hint={`${counts.active_diagnostics ?? 0} still unfixed`}
            />
            <StatTile
              label="At Risk" value={mastery.at_risk_count ?? 0} colour={MASTERY.at_risk}
              hint={`${mastery.strong_count ?? 0} strong · ${mastery.developing_count ?? 0} developing`}
            />
            <StatTile
              label="Remediation" value={counts.completed_remediation_triggers ?? 0} colour={MASTERY.strong}
              hint={`${counts.active_remediation_triggers ?? 0} still open`}
            />
            <StatTile
              label="Quiz Accuracy" value={`${avgAccuracy}%`} colour={avgAccuracy >= 50 ? 'var(--cg-ok)' : 'var(--cg-warn)'}
              hint={`${totalAssessments} taken · ${masteredCount} mastered`}
            />
            <StatTile
              label="Cognitive State" value={String(cognitiveState || '—').split(' ')[0]} colour="var(--cg-accent-bright)"
              hint={cognitiveState || 'not measured'}
            />
          </div>

          {conceptTrends.length > 0 && (
            <div className="cg-section">
              <h3 className="cg-section-title">🎯 Concept Breakdown</h3>
              <div className="cg-flex-col cg-stagger" style={{ gap: '11px' }}>
                {conceptTrends.map((t) => <ConceptRow key={t.concept_tag} trend={t} />)}
              </div>
            </div>
          )}

          {radarData.length > 0 && (
            <div className="cg-section cg-chart-container cg-glass-inner" style={{ padding: '26px' }}>
              <h3 className="cg-section-title cg-text-gradient-primary" style={{ justifyContent: 'center' }}>
                Cognitive Skill Map
              </h3>
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart cx="50%" cy="50%" outerRadius="72%" data={radarData}>
                  <defs>
                    <linearGradient id="colorUv" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={chart.accent} stopOpacity={0.85} />
                      <stop offset="95%" stopColor={chart.accent} stopOpacity={0.28} />
                    </linearGradient>
                  </defs>
                  <PolarGrid stroke={chart.grid} />
                  <PolarAngleAxis dataKey="subject" tick={{ fill: chart.axis, fontSize: 12 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: chart.axis, fontSize: 10 }} />
                  <RechartsTooltip contentStyle={{ background: 'var(--cg-page)', border: '1px solid var(--cg-border)', borderRadius: '10px' }} />
                  <Radar name="Mastery (%)" dataKey="A" stroke={chart.accent} strokeWidth={3} fill="url(#colorUv)" fillOpacity={0.6} />
                </RadarChart>
              </ResponsiveContainer>
              <p className="cg-text-muted" style={{ textAlign: 'center', fontSize: '0.78rem', margin: 0 }}>
                {conceptTrends.length > 0 ? 'Mastery per concept, from Code Coach' : 'Quiz accuracy per concept'}
              </p>
            </div>
          )}

          {timeline.length > 0 && (
            <div className="cg-section">
              <h3 className="cg-section-title">🕒 Recent Activity</h3>
              <div className="cg-timeline">
                {timeline.map((e) => (
                  <div key={e.event_id} className="cg-timeline-item">
                    <div className="cg-timeline-title">
                      <span className="cg-timeline-tag">{titleCase(e.component)}</span>
                      {e.title || e.event_type}
                    </div>
                    {e.summary && <div className="cg-timeline-sub">{e.summary}</div>}
                    {e.occurred_at && (
                      <div className="cg-timeline-time">{new Date(e.occurred_at).toLocaleString()}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="cg-section" style={{ marginBottom: 0 }}>
            <h3 className="cg-section-title">📝 Your Study Guider Quizzes</h3>
            {progressData.length === 0 ? (
              <p className="cg-text-muted" style={{ fontSize: '0.88rem', margin: 0 }}>
                No quizzes completed here yet. Work through a lesson and its quiz to build this up.
              </p>
            ) : (
              <div className="cg-flex-col cg-stagger" style={{ gap: '11px' }}>
                {progressData.map((item, index) => {
                  const pct = Math.round((item.score / item.total) * 100);
                  const good = item.status === 'MASTERED';
                  return (
                    <div key={index} className="cg-concept-row">
                      <div className="cg-concept-top" style={{ marginBottom: '10px' }}>
                        <span className="cg-concept-name">{titleCase(item.concept)}</span>
                        <span className="cg-chip" style={{
                          color: good ? MASTERY.strong : MASTERY.developing,
                          background: `${good ? MASTERY.strong : MASTERY.developing}22`,
                        }}>
                          {item.status} · {item.score}/{item.total}
                        </span>
                      </div>
                      <div className="cg-meter">
                        <div className="cg-meter-fill" style={{
                          width: `${pct}%`,
                          background: `linear-gradient(90deg, ${good ? MASTERY.strong : MASTERY.developing}, ${good ? MASTERY.strong : MASTERY.developing}aa)`,
                        }} />
                      </div>
                      <div className="cg-concept-meta">
                        <span>{pct}% correct</span>
                        {item.last_updated && <span>{new Date(item.last_updated).toLocaleString()}</span>}
                      </div>
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
