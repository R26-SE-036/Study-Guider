import React, { useState, useEffect } from 'react';
import axios from 'axios';

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

  return (
    <div className="cg-card fadeIn" style={{ padding: '40px' }}>
      
      <div className="cg-flex-between" style={{ marginBottom: '40px' }}>
        <div>
          <h2 className="cg-title-section" style={{ fontSize: '1.8rem' }}>Knowledge Graph Analytics</h2>
          <p className="cg-text-muted">Real-time mastery tracking from Neo4j</p>
        </div>
        <button onClick={onBack} className="cg-btn-outline" style={{ padding: '8px 16px', borderRadius: '6px', fontSize: '0.9rem', cursor: 'pointer' }}>
          Close Analytics
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#94A3B8' }}>
          <div style={{animation: 'pulse 1s infinite'}}>Fetching graph nodes...</div>
        </div>
      ) : (!progressData || progressData.length === 0) ? (
        <div style={{ textAlign: 'center', padding: '60px 0', backgroundColor: '#0F172A', borderRadius: '8px', border: '1px dashed #334155' }}>
          <h3 className="cg-title-content" style={{color: '#94A3B8'}}>No Data Points Found</h3>
          <p className="cg-text-muted">Ensure Neo4j is connected and complete an assessment.</p>
        </div>
      ) : (
        <div className="cg-flex-col" style={{ gap: '20px' }}>
          {progressData.map((item, index) => {
            const isMastered = item.status === "MASTERED";
            const scorePercentage = (item.score / item.total) * 100;
            
            return (
              <div key={index} style={{ 
                padding: '25px', backgroundColor: '#0F172A', borderRadius: '8px', border: '1px solid #334155',
                borderLeft: isMastered ? '4px solid #10B981' : '4px solid #F59E0B'
              }}>
                <div className="cg-flex-between" style={{ marginBottom: '20px' }}>
                  <div>
                    <h3 className="cg-title-content" style={{ fontSize: '1.2rem', fontFamily: 'Fira Code' }}>
                      {item.concept}
                    </h3>
                    <span style={{ fontSize: '0.8rem', color: '#64748B' }}>
                      {new Date(item.last_updated).toLocaleString()}
                    </span>
                  </div>
                  
                  <div style={{ 
                    padding: '6px 12px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', letterSpacing: '1px',
                    backgroundColor: isMastered ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                    color: isMastered ? '#34D399' : '#FBBF24',
                  }}>
                    {item.status}
                  </div>
                </div>

                <div>
                  <div className="cg-flex-between" style={{ marginBottom: '8px', fontSize: '0.85rem' }}>
                    <span className="cg-text-muted">Validation Accuracy</span>
                    <span style={{ color: '#F8FAFC', fontWeight: '600' }}>{item.score} / {item.total}</span>
                  </div>
                  <div style={{ width: '100%', backgroundColor: '#1E293B', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
                    <div style={{ 
                      height: '100%', 
                      backgroundColor: isMastered ? '#10B981' : '#F59E0B',
                      width: `${scorePercentage}%`,
                      transition: 'width 1s cubic-bezier(0.16, 1, 0.3, 1)'
                    }}></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}