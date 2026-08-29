import React, { useState, useEffect } from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip as RechartsTooltip
} from 'recharts';

import api from '../lib/api';

// No studentId prop: the backend reads the student from the bearer token, so
// there is no id for this component to pass around or get wrong.
export default function StudentDashboard({ cognitiveState, onBack }) {
  const [progressData, setProgressData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/progress/me')
      .then(response => {
        if (response.data.success && response.data.data) {
          setProgressData(response.data.data);
        } else {
          setProgressData([]); 
        }
        setLoading(false);
      })
      .catch(error => {
        console.error("Failed to fetch progress:", error);
        setProgressData([]); 
        setLoading(false);
      });
  }, []);

  const totalAssessments = progressData.length;
  const masteredCount = progressData.filter(item => item.status === "MASTERED").length;
  const avgAccuracy = totalAssessments > 0 
    ? Math.round((progressData.reduce((acc, curr) => acc + (curr.score / curr.total), 0) / totalAssessments) * 100) 
    : 0;

  const conceptStats = progressData.reduce((acc, curr) => {
    if (!acc[curr.concept]) {
      acc[curr.concept] = { concept: curr.concept, totalScore: 0, maxPossible: 0 };
    }
    acc[curr.concept].totalScore += curr.score;
    acc[curr.concept].maxPossible += curr.total;
    return acc;
  }, {});

  const radarData = Object.values(conceptStats).map(stat => ({
    subject: stat.concept.replace(/_/g, ' '),
    A: Math.round((stat.totalScore / stat.maxPossible) * 100),
    fullMark: 100
  }));

  return (
    <div className="cg-card fadeIn cg-glass-panel" style={{ padding: '50px' }}>
      
      <div className="cg-flex-between" style={{ marginBottom: '40px', paddingBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div style={{ width: '50px', height: '50px', background: 'linear-gradient(135deg, #3B82F6, #8B5CF6)', borderRadius: '12px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', boxShadow: '0 10px 20px rgba(59, 130, 246, 0.3)' }}>📊</div>
          <div>
            <h2 className="cg-title-section" style={{ fontSize: '2rem', margin: 0 }}>Knowledge Graph Analytics</h2>
            <p className="cg-text-muted" style={{ margin: '5px 0 0 0', fontSize: '1rem' }}>Real-time mastery tracking & skill visualization</p>
          </div>
        </div>
        <button onClick={onBack} className="cg-btn-outline" style={{ padding: '10px 20px', borderRadius: '8px', fontSize: '0.95rem' }}>
          ✕ Close
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <div className="spinner" style={{ fontSize: '2.5rem', marginBottom: '20px' }}>🕸️</div>
          <h3 className="cg-title-section cg-text-gradient-primary">Syncing with Neo4j...</h3>
        </div>
      ) : (!progressData || progressData.length === 0) ? (
        <div className="cg-glass-inner" style={{ textAlign: 'center', padding: '80px 0', borderRadius: '16px', border: '1px dashed rgba(148, 163, 184, 0.3)' }}>
          <div style={{ fontSize: '4rem', opacity: '0.5', marginBottom: '20px' }}>📭</div>
          <h3 className="cg-title-content" style={{color: '#94A3B8', fontSize: '1.5rem'}}>No Data Points Found</h3>
          <p className="cg-text-muted" style={{ fontSize: '1.1rem' }}>Ensure Neo4j is connected and complete an assessment.</p>
        </div>
      ) : (
        <div className="cg-flex-col" style={{ gap: '40px' }}>
          
          {/* 🌟 1. OVERALL PROGRESS SUMMARY CARDS (Now with 4 Cards including Resilience) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '20px' }}>
            <div className="cg-stat-card cg-glass-inner" style={{ padding: '25px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8rem', marginBottom: '8px' }}>📝</div>
              <p className="cg-text-muted" style={{ margin: '0 0 8px 0', fontSize: '0.9rem', fontWeight: '600', letterSpacing: '1px' }}>Assessments</p>
              <h1 style={{ margin: 0, color: '#60A5FA', fontSize: '2.4rem', textShadow: '0 0 20px rgba(96, 165, 250, 0.4)' }}>{totalAssessments}</h1>
            </div>

            <div className="cg-stat-card cg-glass-inner" style={{ padding: '25px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8rem', marginBottom: '8px' }}>🎯</div>
              <p className="cg-text-muted" style={{ margin: '0 0 8px 0', fontSize: '0.9rem', fontWeight: '600', letterSpacing: '1px' }}>Avg Accuracy</p>
              <h1 style={{ margin: 0, color: avgAccuracy >= 50 ? '#34D399' : '#FBBF24', fontSize: '2.4rem', textShadow: `0 0 20px ${avgAccuracy >= 50 ? 'rgba(52, 211, 153, 0.4)' : 'rgba(251, 191, 36, 0.4)'}` }}>{avgAccuracy}%</h1>
            </div>

            <div className="cg-stat-card cg-glass-inner" style={{ padding: '25px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8rem', marginBottom: '8px' }}>🎓</div>
              <p className="cg-text-muted" style={{ margin: '0 0 8px 0', fontSize: '0.9rem', fontWeight: '600', letterSpacing: '1px' }}>Mastered</p>
              <h1 style={{ margin: 0, color: '#A78BFA', fontSize: '2.4rem', textShadow: '0 0 20px rgba(167, 139, 250, 0.4)' }}>{masteredCount}</h1>
            </div>

            <div className="cg-stat-card cg-glass-inner" style={{ padding: '25px 20px', textAlign: 'center' }}>
              <div style={{ fontSize: '1.8rem', marginBottom: '8px' }}>🔥</div>
              <p className="cg-text-muted" style={{ margin: '0 0 8px 0', fontSize: '0.9rem', fontWeight: '600', letterSpacing: '1px' }}>Resilience Streak</p>
              <h1 style={{ margin: 0, color: '#F472B6', fontSize: '2.4rem', textShadow: '0 0 20px rgba(244, 114, 182, 0.4)' }}>
                {totalAssessments > 0 ? `${totalAssessments}x` : '0x'}
              </h1>
            </div>
          </div>

          {/* 🕸️ 2. VISUAL SKILL RADAR CHART */}
          {radarData.length > 0 && (
            <div className="cg-chart-container cg-glass-inner" style={{ padding: '40px', position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: '-100px', right: '-100px', width: '300px', height: '300px', background: 'radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%)', filter: 'blur(40px)', zIndex: 0 }}></div>
              <h3 className="cg-title-content cg-text-gradient-primary" style={{ textAlign: 'center', marginBottom: '30px', fontSize: '1.5rem', position: 'relative', zIndex: 1 }}>Cognitive Skill Map</h3>
              <div style={{ width: '100%', height: '400px', position: 'relative', zIndex: 1 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                    <PolarGrid stroke="rgba(255,255,255,0.1)" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#E2E8F0', fontSize: 13, fontFamily: 'Inter', fontWeight: 500 }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#64748B' }} axisLine={false} />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: 'rgba(15, 23, 42, 0.9)', border: '1px solid rgba(59, 130, 246, 0.5)', borderRadius: '12px', color: '#F8FAFC', backdropFilter: 'blur(8px)', boxShadow: '0 10px 25px rgba(0,0,0,0.5)' }}
                    />
                    <Radar name="Mastery (%)" dataKey="A" stroke="#8B5CF6" strokeWidth={3} fill="url(#colorUv)" fillOpacity={0.6} />
                    <defs>
                      <linearGradient id="colorUv" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.8}/>
                        <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.2}/>
                      </linearGradient>
                    </defs>
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* 📜 3. INDIVIDUAL HISTORY TIMELINE */}
          <div>
            <h3 className="cg-title-content" style={{ marginBottom: '30px', display: 'flex', alignItems: 'center', gap: '10px', fontSize: '1.4rem' }}>
              <span>🕰️</span> Assessment History
            </h3>
            <div className="cg-flex-col" style={{ gap: '16px' }}>
              {progressData.map((item, index) => {
                const isMastered = item.status === "MASTERED";
                const scorePercentage = (item.score / item.total) * 100;
                
                return (
                  <div key={index} className="cg-history-card cg-glass-inner" style={{ 
                    padding: '25px', 
                    borderLeft: isMastered ? '4px solid #10B981' : '4px solid #F87171',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '20px'
                  }}>
                    <div>
                      <h4 style={{ margin: '0 0 8px 0', color: '#F8FAFC', fontFamily: 'Fira Code', fontSize: '1.15rem', letterSpacing: '-0.5px' }}>
                        {item.concept}
                      </h4>
                      <span style={{ fontSize: '0.85rem', color: '#94A3B8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        📅 {new Date(item.last_updated).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', gap: '30px' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#F8FAFC', fontWeight: '700', fontSize: '1.2rem' }}>{item.score} <span style={{color: '#64748B'}}>/</span> {item.total}</div>
                        <div style={{ fontSize: '0.85rem', color: isMastered ? '#34D399' : '#F87171', fontWeight: '500' }}>{scorePercentage.toFixed(0)}% Accuracy</div>
                      </div>
                      
                      <div style={{ 
                        padding: '8px 16px', borderRadius: '30px', fontSize: '0.8rem', fontWeight: '700', letterSpacing: '1px',
                        background: isMastered ? 'linear-gradient(90deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%)' : 'linear-gradient(90deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%)',
                        color: isMastered ? '#10B981' : '#EF4444',
                        border: `1px solid ${isMastered ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                        minWidth: '120px', textAlign: 'center',
                        boxShadow: isMastered ? '0 0 15px rgba(16, 185, 129, 0.1)' : '0 0 15px rgba(239, 68, 68, 0.1)'
                      }}>
                        {item.status}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}