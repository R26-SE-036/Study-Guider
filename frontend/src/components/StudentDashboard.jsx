import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip as RechartsTooltip
} from 'recharts';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function StudentDashboard({ studentId, onBack }) {
  const [progressData, setProgressData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API_BASE_URL}/api/progress/${studentId}`)
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
  }, [studentId]);

  // ==========================================
  // 📊 ANALYTICS CALCULATIONS
  // ==========================================
  const totalAssessments = progressData.length;
  const masteredCount = progressData.filter(item => item.status === "MASTERED").length;
  const avgAccuracy = totalAssessments > 0 
    ? Math.round((progressData.reduce((acc, curr) => acc + (curr.score / curr.total), 0) / totalAssessments) * 100) 
    : 0;

  // Process Data for Radar Chart (Group by Concept)
  const conceptStats = progressData.reduce((acc, curr) => {
    if (!acc[curr.concept]) {
      acc[curr.concept] = { concept: curr.concept, totalScore: 0, maxPossible: 0 };
    }
    acc[curr.concept].totalScore += curr.score;
    acc[curr.concept].maxPossible += curr.total;
    return acc;
  }, {});

  const radarData = Object.values(conceptStats).map(stat => ({
    subject: stat.concept.replace(/_/g, ' '), // Make concept name readable
    A: Math.round((stat.totalScore / stat.maxPossible) * 100),
    fullMark: 100
  }));

  return (
    <div className="cg-card fadeIn" style={{ padding: '40px' }}>
      
      <div className="cg-flex-between" style={{ marginBottom: '40px' }}>
        <div>
          <h2 className="cg-title-section" style={{ fontSize: '1.8rem' }}>Knowledge Graph Analytics</h2>
          <p className="cg-text-muted">Real-time mastery tracking & skill visualization</p>
        </div>
        <button onClick={onBack} className="cg-btn-outline" style={{ padding: '8px 16px', borderRadius: '6px', fontSize: '0.9rem', cursor: 'pointer' }}>
          Close Analytics
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8' }}>
          <div style={{animation: 'pulse 1s infinite'}}>Fetching graph nodes from Neo4j...</div>
        </div>
      ) : (!progressData || progressData.length === 0) ? (
        <div style={{ textAlign: 'center', padding: '60px 0', backgroundColor: '#0F172A', borderRadius: '8px', border: '1px dashed #334155' }}>
          <h3 className="cg-title-content" style={{color: '#94A3B8'}}>No Data Points Found</h3>
          <p className="cg-text-muted">Ensure Neo4j is connected and complete an assessment.</p>
        </div>
      ) : (
        <div className="cg-flex-col" style={{ gap: '40px' }}>
          
          {/* 🌟 1. OVERALL PROGRESS SUMMARY CARDS */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px' }}>
            <div className="cg-stat-card" style={{ backgroundColor: '#0F172A', padding: '20px', borderRadius: '12px', border: '1px solid #334155', textAlign: 'center' }}>
              <p className="cg-text-muted" style={{ margin: '0 0 10px 0', fontSize: '0.9rem', textTransform: 'uppercase' }}>Assessments Taken</p>
              <h1 style={{ margin: 0, color: '#3B82F6', fontSize: '2.5rem' }}>{totalAssessments}</h1>
            </div>
            <div className="cg-stat-card" style={{ backgroundColor: '#0F172A', padding: '20px', borderRadius: '12px', border: '1px solid #334155', textAlign: 'center' }}>
              <p className="cg-text-muted" style={{ margin: '0 0 10px 0', fontSize: '0.9rem', textTransform: 'uppercase' }}>Average Accuracy</p>
              <h1 style={{ margin: 0, color: avgAccuracy >= 50 ? '#10B981' : '#F59E0B', fontSize: '2.5rem' }}>{avgAccuracy}%</h1>
            </div>
            <div className="cg-stat-card" style={{ backgroundColor: '#0F172A', padding: '20px', borderRadius: '12px', border: '1px solid #334155', textAlign: 'center' }}>
              <p className="cg-text-muted" style={{ margin: '0 0 10px 0', fontSize: '0.9rem', textTransform: 'uppercase' }}>Concepts Mastered</p>
              <h1 style={{ margin: 0, color: '#A78BFA', fontSize: '2.5rem' }}>{masteredCount}</h1>
            </div>
          </div>

          {/* 🕸️ 2. VISUAL SKILL RADAR CHART */}
          {radarData.length > 0 && (
            <div className="cg-chart-container" style={{ backgroundColor: '#0F172A', padding: '30px', borderRadius: '12px', border: '1px solid #334155' }}>
              <h3 className="cg-title-content" style={{ textAlign: 'center', marginBottom: '20px' }}>Cognitive Skill Map</h3>
              <div style={{ width: '100%', height: '350px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="70%" data={radarData}>
                    <PolarGrid stroke="#334155" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#94A3B8', fontSize: 12, fontFamily: 'Fira Code' }} />
                    <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: '#475569' }} />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#1E293B', border: '1px solid #3B82F6', borderRadius: '8px', color: '#F8FAFC' }}
                    />
                    <Radar name="Mastery (%)" dataKey="A" stroke="#3B82F6" fill="#3B82F6" fillOpacity={0.4} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* 📜 3. INDIVIDUAL HISTORY TIMELINE */}
          <div>
            <h3 className="cg-title-content" style={{ marginBottom: '20px', borderBottom: '1px solid #334155', paddingBottom: '10px' }}>Assessment History</h3>
            <div className="cg-flex-col" style={{ gap: '15px' }}>
              {progressData.map((item, index) => {
                const isMastered = item.status === "MASTERED";
                const scorePercentage = (item.score / item.total) * 100;
                
                return (
                  <div key={index} className="cg-history-card" style={{ 
                    padding: '20px', backgroundColor: '#0F172A', borderRadius: '8px', border: '1px solid #334155',
                    borderLeft: isMastered ? '4px solid #10B981' : '4px solid #F87171',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px'
                  }}>
                    <div>
                      <h4 style={{ margin: '0 0 5px 0', color: '#E2E8F0', fontFamily: 'Fira Code', fontSize: '1.1rem' }}>
                        {item.concept}
                      </h4>
                      <span style={{ fontSize: '0.8rem', color: '#64748B' }}>
                        {new Date(item.last_updated).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#F8FAFC', fontWeight: 'bold', fontSize: '1.1rem' }}>{item.score} / {item.total}</div>
                        <div style={{ fontSize: '0.8rem', color: isMastered ? '#34D399' : '#F87171' }}>{scorePercentage.toFixed(0)}% Accuracy</div>
                      </div>
                      
                      <div style={{ 
                        padding: '6px 12px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', letterSpacing: '1px',
                        backgroundColor: isMastered ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        color: isMastered ? '#34D399' : '#F87171',
                        minWidth: '110px', textAlign: 'center'
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