import React, { useState, useEffect } from 'react';
import api from '../lib/api';

/**
 * The validation quiz for one remediation trigger.
 *
 * Finishing it does two things: it records the attempt in Study Guider's own
 * Neo4j progress graph, and it reports the score back to Code Coach. That
 * second call is what closes the loop — a score at or above the platform pass
 * mark marks the trigger completed, and without it Code Coach would keep
 * insisting the student is still struggling with this concept.
 */
export default function ValidationQuiz({ trigger, errorType, onComplete }) {
  const [quizState, setQuizState] = useState(() => {
    const saved = localStorage.getItem('cg_quizState');
    return saved ? JSON.parse(saved) : {
      quizData: null,
      currentQIndex: 0,
      selectedOption: null,
      confidenceLevel: "medium", // 🤔 New Metacognition State: 'low', 'medium', 'high'
      isAnswerChecked: false,
      score: 0,
      quizFinished: false,
      graphStatus: "pending"
    };
  });

  const [quizLoading, setQuizLoading] = useState(!quizState.quizData);

  useEffect(() => {
    localStorage.setItem('cg_quizState', JSON.stringify(quizState));
  }, [quizState]);

  useEffect(() => {
    if (!quizState.quizData) {
      // No student_id: the backend takes the student from the bearer token.
      const payload = { error_type: errorType };
      api.post('/api/quiz/generate', payload)
        .then(response => {
          if (response.data.quiz_data && response.data.quiz_data.length > 0) {
            setQuizState(prev => ({ ...prev, quizData: response.data.quiz_data }));
          }
          setQuizLoading(false);
        })
        .catch(error => {
          console.error("Quiz Error:", error);
          setQuizLoading(false);
        });
    }
  }, [errorType, quizState.quizData]);

  const isMatch = (opt1, opt2) => {
    if (!opt1 || !opt2) return false;
    const s1 = String(opt1).toLowerCase().trim();
    const s2 = String(opt2).toLowerCase().trim();
    return s1 === s2 || s1.includes(s2) || s2.includes(s1);
  };

  const checkAnswer = () => {
    setQuizState(prev => {
      const correctAns = prev.quizData[prev.currentQIndex]?.correct_answer;
      const isCorrect = isMatch(prev.selectedOption, correctAns);
      return {
        ...prev,
        isAnswerChecked: true,
        score: isCorrect ? prev.score + 1 : prev.score
      };
    });
  };

  const handleQuizCompletion = (finalScore, totalQs) => {
    setQuizState(prev => ({ ...prev, quizFinished: true, graphStatus: "updating" }));

    // 1. Study Guider's own record of the attempt. No student_id — the backend
    //    resolves the student from the bearer token.
    api.post('/api/progress/update', {
        concept: errorType,
        score: finalScore,
        total_questions: totalQs
    })
      .then(response => {
        setQuizState(prev => ({ ...prev, graphStatus: response.data.success ? "success" : "error" }));
      })
      .catch(error => {
        console.error("Neo4j Update Error:", error);
        setQuizState(prev => ({ ...prev, graphStatus: "error" }));
      });

    // 2. Report the result to Code Coach. This is the call that resolves the
    //    remediation trigger, so it is tracked separately from the Neo4j write
    //    above — one can fail without hiding the other.
    if (trigger?.trigger_id) {
      const scorePercent = totalQs > 0 ? Math.round((finalScore / totalQs) * 100) : 0;

      setQuizState(prev => ({ ...prev, triggerStatus: "updating" }));
      api.post(`/api/remediation/triggers/${trigger.trigger_id}/quiz-completed`, {
          quiz_id: trigger.quiz?.quiz_id || 'quiz_general_01',
          score_percent: scorePercent
          // `passed` is left out on purpose: Code Coach applies the platform
          // pass mark, so Study Guider cannot quietly disagree about it.
      })
        .then(response => {
          setQuizState(prev => ({
            ...prev,
            triggerStatus: "success",
            triggerResolved: response.data.trigger?.status === "completed",
            triggerPassed: response.data.trigger?.quiz_passed
          }));
        })
        .catch(error => {
          console.error("Code Coach trigger update failed:", error);
          setQuizState(prev => ({ ...prev, triggerStatus: "error" }));
        });
    }
  };

  const nextQuestion = () => {
    if (quizState.currentQIndex < quizState.quizData.length - 1) {
      setQuizState(prev => ({
        ...prev,
        currentQIndex: prev.currentQIndex + 1,
        selectedOption: null,
        confidenceLevel: "medium",
        isAnswerChecked: false
      }));
    } else {
      handleQuizCompletion(quizState.score, quizState.quizData.length);
    }
  };

  if (quizState.quizFinished) {
    const passed = quizState.score >= (quizState.quizData?.length / 2);
    return (
      <div className="cg-card ValidationQuiz fadeIn cg-glass-panel" style={{ textAlign: 'center', padding: '60px 40px' }}>
        <div style={{ fontSize: '4rem', marginBottom: '20px' }}>{passed ? '🏆' : '📚'}</div>
        <h2 className="cg-title-section" style={{ fontSize: '2.5rem', background: passed ? 'linear-gradient(to right, #34D399, #10B981)' : 'linear-gradient(to right, #F87171, #EF4444)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          Assessment Complete
        </h2>
        
        <div style={{ margin: '40px 0', padding: '30px', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <span className="cg-text-muted" style={{ fontSize: '1.2rem', textTransform: 'uppercase', letterSpacing: '2px', fontWeight: '600' }}>Final Score</span>
          <h1 style={{ fontSize: '5rem', margin: '15px 0', color: passed ? '#34D399' : '#F87171', textShadow: `0 0 30px ${passed ? 'rgba(52, 211, 153, 0.3)' : 'rgba(248, 113, 113, 0.3)'}` }}>
            {quizState.score}<span style={{color: '#475569', fontSize: '4rem'}}>/</span>{quizState.quizData?.length || 4}
          </h1>
        </div>

        <div style={{ marginTop: '40px', paddingTop: '30px', borderTop: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
          <h4 className="cg-title-content" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}><span>🔄</span> Database Sync Status</h4>
          {quizState.graphStatus === "updating" && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(245, 158, 11, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #FBBF24', color: '#FCD34D'}}>⏳ Committing results to Neo4j Knowledge Graph...</div>}
          {quizState.graphStatus === "success" && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #10B981', color: '#6EE7B7'}}>✅ Neo4j Database Sync Successful! Relationship updated.</div>}
          {quizState.graphStatus === "error" && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #EF4444', color: '#FCA5A5'}}>❌ Database Connection Failed. Please check Backend configurations.</div>}

          {/* The half that matters to the rest of the platform: until Code
              Coach records this score, it still considers the student stuck. */}
          {trigger?.trigger_id && (
            <>
              <h4 className="cg-title-content" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '28px' }}><span>🎯</span> Code Coach Remediation</h4>
              {quizState.triggerStatus === "updating" && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(245, 158, 11, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #FBBF24', color: '#FCD34D'}}>⏳ Reporting your score to Code Coach...</div>}
              {quizState.triggerStatus === "success" && quizState.triggerResolved && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #10B981', color: '#6EE7B7'}}>✅ Passed. This struggle is marked resolved and will stop being flagged.</div>}
              {quizState.triggerStatus === "success" && !quizState.triggerResolved && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(245, 158, 11, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #FBBF24', color: '#FCD34D'}}>📌 Score recorded, but below the pass mark — this concept will stay on your list.</div>}
              {quizState.triggerStatus === "error" && <div className="cg-feedback-box" style={{background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.1) 0%, transparent 100%)', borderLeft: '4px solid #EF4444', color: '#FCA5A5'}}>❌ Could not reach Code Coach. Your score was not recorded there, so this concept stays flagged.</div>}
            </>
          )}
        </div>

        <button
          onClick={() => { localStorage.removeItem('cg_quizState'); onComplete?.(); }}
          className="cg-btn cg-btn-premium-success"
          style={{ marginTop: '36px', padding: '14px 32px' }}
        >
          Back to my lessons
        </button>
      </div>
    );
  }

  const currentCorrectAnswer = quizState.quizData?.[quizState.currentQIndex]?.correct_answer;
  const isUserCorrect = isMatch(quizState.selectedOption, currentCorrectAnswer);
  const progressPercentage = quizState.quizData ? ((quizState.currentQIndex + 1) / quizState.quizData.length) * 100 : 0;

  // 🤔 Metacognitive Feedback Analysis
  const getMetacognitiveMessage = () => {
    if (isUserCorrect && quizState.confidenceLevel === "high") {
      return { tag: "🌟 Mastery Confirmed", text: "You were fully confident and applied the correct logical principle perfectly!" };
    }
    if (isUserCorrect && quizState.confidenceLevel === "low") {
      return { tag: "💡 Knowledge Solidifier", text: "You got it right! Review the explanation below to turn your intuition into confident mastery." };
    }
    if (!isUserCorrect && quizState.confidenceLevel === "high") {
      return { tag: "⚠️ Misconception Alert", text: "You were confident, but this reveals a common conceptual blind spot. Study the breakdown carefully!" };
    }
    return { tag: "🛠️ Normal Learning Step", text: "Good attempt. Practice and conceptual reflection are the keys to mastering Java logic." };
  };

  const metaInsight = getMetacognitiveMessage();

  return (
    <div className="cg-card ValidationQuiz fadeIn cg-glass-panel">
      {quizLoading || !quizState.quizData ? (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <div className="spinner" style={{ fontSize: '3rem', display: 'inline-block', marginBottom: '20px' }}>🧠</div>
          <h3 className="cg-title-section cg-text-gradient-primary" style={{ fontSize: '1.8rem' }}>Generating AI Assessment...</h3>
          <p className="cg-text-muted" style={{ fontSize: '1.1rem' }}>Analyzing your code context to build highly relevant questions.</p>
        </div>
      ) : (
        <div>
          {/* Progress Bar */}
          <div style={{ width: '100%', height: '6px', background: '#1E293B', borderRadius: '10px', marginBottom: '30px', overflow: 'hidden' }}>
            <div style={{ width: `${progressPercentage}%`, height: '100%', background: 'linear-gradient(90deg, #3B82F6, #8B5CF6)', transition: 'width 0.5s ease' }}></div>
          </div>

          <div className="cg-flex-between" style={{ marginBottom: '30px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ padding: '6px 12px', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '6px', fontSize: '0.85rem', color: '#60A5FA', fontWeight: '600', letterSpacing: '1px' }}>
                Q {quizState.currentQIndex + 1} OF {quizState.quizData.length}
              </span>
            </div>
            <span className="cg-badge-outline">{errorType}</span>
          </div>
          
          <h3 className="cg-title-section" style={{ fontSize: '1.4rem', marginBottom: '35px', lineHeight: '1.6', fontWeight: '500' }}>
            {quizState.quizData[quizState.currentQIndex]?.question}
          </h3>
          
          <div className="cg-flex-col" style={{ gap: '16px', marginBottom: '25px' }}>
            {quizState.quizData[quizState.currentQIndex]?.options?.map((option, idx) => {
              
              const isCorrectAnswer = isMatch(option, currentCorrectAnswer);
              const isSelected = quizState.selectedOption === option;
              const isSelectedWrong = isSelected && !isCorrectAnswer;
              
              let buttonClass = 'cg-quiz-option ';
              if (isSelected) buttonClass += 'selected ';
              if (quizState.isAnswerChecked && isCorrectAnswer) buttonClass += 'correct ';
              if (quizState.isAnswerChecked && isSelectedWrong) buttonClass += 'incorrect ';

              return (
                <button 
                  key={idx}
                  onClick={() => !quizState.isAnswerChecked && setQuizState(prev => ({ ...prev, selectedOption: option }))}
                  disabled={quizState.isAnswerChecked}
                  className={buttonClass.trim()}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                    <div className="cg-option-circle">
                      {quizState.isAnswerChecked && isCorrectAnswer ? '✓' : (quizState.isAnswerChecked && isSelectedWrong ? '✕' : String.fromCharCode(65 + idx))}
                    </div>
                    <span>{option}</span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* 🤔 Metacognition Confidence Selector (Before Submit) */}
          {!quizState.isAnswerChecked && quizState.selectedOption && (
            <div className="fadeIn" style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '16px 20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '25px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
              <span style={{ fontSize: '0.9rem', color: '#94A3B8', fontWeight: '500' }}>
                How confident are you in this answer?
              </span>
              <div style={{ display: 'flex', gap: '8px' }}>
                {[
                  { id: 'low', label: 'Guessing 🤔' },
                  { id: 'medium', label: 'Fairly Sure 👍' },
                  { id: 'high', label: '100% Confident 🚀' }
                ].map(item => (
                  <button
                    key={item.id}
                    onClick={() => setQuizState(prev => ({ ...prev, confidenceLevel: item.id }))}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '8px',
                      fontSize: '0.8rem',
                      cursor: 'pointer',
                      border: quizState.confidenceLevel === item.id ? '1px solid #3B82F6' : '1px solid rgba(255,255,255,0.1)',
                      backgroundColor: quizState.confidenceLevel === item.id ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                      color: quizState.confidenceLevel === item.id ? '#60A5FA' : '#94A3B8'
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Dynamic Feedback + Metacognitive Insight Box */}
          {quizState.isAnswerChecked && (
            <div className={`cg-feedback-box fadeIn ${isUserCorrect ? 'cg-feedback-success' : 'cg-feedback-error'}`} style={{ padding: '25px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h4 style={{ margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '10px', color: isUserCorrect ? '#34D399' : '#F87171' }}>
                  {isUserCorrect ? '✅ Outstanding!' : '❌ Let\'s Review'}
                </h4>
                <span style={{ fontSize: '0.8rem', fontWeight: 'bold', padding: '4px 10px', borderRadius: '6px', background: 'rgba(255,255,255,0.1)', color: '#F8FAFC' }}>
                  {metaInsight.tag}
                </span>
              </div>
              <p style={{ margin: '0 0 10px 0', color: '#CBD5E1', fontSize: '0.9rem', fontStyle: 'italic' }}>
                {metaInsight.text}
              </p>
              <p style={{ margin: 0, color: '#F1F5F9', lineHeight: '1.6', fontSize: '1.05rem', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '10px' }}>
                {quizState.quizData[quizState.currentQIndex]?.explanation}
              </p>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '25px', paddingTop: '25px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            {!quizState.isAnswerChecked ? (
              <button 
                onClick={checkAnswer} 
                disabled={!quizState.selectedOption} 
                className={`cg-btn ${quizState.selectedOption ? 'cg-btn-premium-primary' : 'cg-btn-outline'}`}
                style={{ padding: '14px 30px', fontSize: '1.05rem' }}
              >
                Submit Answer
              </button>
            ) : (
              <button onClick={nextQuestion} className="cg-btn cg-btn-premium-primary" style={{ padding: '14px 30px', fontSize: '1.05rem' }}>
                {quizState.currentQIndex < quizState.quizData.length - 1 ? "Next Question →" : "Complete Assessment →"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}