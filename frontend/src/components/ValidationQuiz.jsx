import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function ValidationQuiz({ studentId, errorType, codeSnippet }) {
  const [quizState, setQuizState] = useState(() => {
    const saved = localStorage.getItem('cg_quizState');
    return saved ? JSON.parse(saved) : {
      quizData: null,
      currentQIndex: 0,
      selectedOption: null,
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
      const payload = { student_id: studentId, error_type: errorType, code_snippet: codeSnippet };
      axios.post(`${API_BASE_URL}/api/quiz/generate`, payload)
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
  }, [studentId, errorType, codeSnippet]);

  // 🚀 Helper function for smart string matching (handles AI inconsistencies)
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

    const payload = { 
        student_id: studentId, 
        concept: errorType, 
        score: finalScore, 
        total_questions: totalQs 
    };

    axios.post(`${API_BASE_URL}/api/progress/update`, payload)
      .then(response => { 
        setQuizState(prev => ({ ...prev, graphStatus: response.data.success ? "success" : "error" })); 
      })
      .catch(error => { 
        console.error("Neo4j Update Error:", error); 
        setQuizState(prev => ({ ...prev, graphStatus: "error" })); 
      });
  };

  const nextQuestion = () => {
    if (quizState.currentQIndex < quizState.quizData.length - 1) {
      setQuizState(prev => ({
        ...prev,
        currentQIndex: prev.currentQIndex + 1,
        selectedOption: null,
        isAnswerChecked: false
      }));
    } else {
      handleQuizCompletion(quizState.score, quizState.quizData.length);
    }
  };

  if (quizState.quizFinished) {
    const passed = quizState.score >= (quizState.quizData?.length / 2);
    return (
      <div className="cg-card ValidationQuiz fadeIn" style={{ textAlign: 'center', padding: '50px 30px' }}>
        <h2 className="cg-title-section" style={{ fontSize: '2rem' }}>Assessment Complete</h2>
        <div style={{ margin: '30px 0' }}>
          <span className="cg-text-muted" style={{ fontSize: '1.2rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Final Score</span>
          <h1 style={{ fontSize: '4rem', margin: '10px 0', color: passed ? '#34D399' : '#F87171' }}>
            {quizState.score}<span style={{color: '#475569'}}>/</span>{quizState.quizData?.length || 4}
          </h1>
        </div>

        <div style={{ marginTop: '40px', paddingTop: '30px', borderTop: '1px solid #334155', textAlign: 'left' }}>
          <h4 className="cg-title-content">Database Sync Status</h4>
          {quizState.graphStatus === "updating" && <div className="cg-feedback-box" style={{backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#FBBF24'}}>⏳ Committing results to Neo4j Knowledge Graph...</div>}
          {quizState.graphStatus === "success" && <div className="cg-feedback-box cg-feedback-success">✅ Neo4j Database Sync Successful! Relationship updated.</div>}
          {quizState.graphStatus === "error" && <div className="cg-feedback-box cg-feedback-error">❌ Database Connection Failed. Please check Backend configurations.</div>}
        </div>
      </div>
    );
  }

  // 🚀 Determine if user got it right for the feedback box
  const currentCorrectAnswer = quizState.quizData?.[quizState.currentQIndex]?.correct_answer;
  const isUserCorrect = isMatch(quizState.selectedOption, currentCorrectAnswer);

  return (
    <div className="cg-card ValidationQuiz fadeIn">
      {quizLoading || !quizState.quizData ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <h3 className="cg-title-section" style={{ color: '#3B82F6' }}>Generating AI Assessment...</h3>
          <p className="cg-text-muted">Analyzing your code context to build relevant questions.</p>
        </div>
      ) : (
        <div>
          <div className="cg-flex-between" style={{ marginBottom: '30px' }}>
            <span className="cg-text-muted" style={{fontFamily: 'Fira Code', fontSize: '0.9rem'}}>
              QUESTION {quizState.currentQIndex + 1}/{quizState.quizData.length}
            </span>
            <span style={{ padding: '4px 10px', backgroundColor: '#0F172A', borderRadius: '4px', fontSize: '0.8rem', color: '#94A3B8', border: '1px solid #334155' }}>
              {errorType}
            </span>
          </div>
          
          <h3 className="cg-title-section" style={{ fontSize: '1.3rem', marginBottom: '30px', lineHeight: '1.5' }}>
            {quizState.quizData[quizState.currentQIndex]?.question}
          </h3>
          
          <div className="cg-flex-col" style={{ gap: '15px', marginBottom: '30px' }}>
            {quizState.quizData[quizState.currentQIndex]?.options?.map((option, idx) => {
              
              // 🚀 Smart logic to determine highlight colors
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
                  {option}
                </button>
              );
            })}
          </div>

          {/* 🚀 Dynamic Feedback Box */}
          {quizState.isAnswerChecked && (
            <div className={`cg-feedback-box ${isUserCorrect ? 'cg-feedback-success' : 'cg-feedback-error'}`}>
              <h4 style={{ margin: '0 0 8px 0', color: isUserCorrect ? '#34D399' : '#F87171' }}>
                {isUserCorrect ? "Correct!" : "Incorrect"}
              </h4>
              <p style={{ margin: 0, color: '#E2E8F0' }}>{quizState.quizData[quizState.currentQIndex]?.explanation}</p>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
            {!quizState.isAnswerChecked ? (
              <button onClick={checkAnswer} disabled={!quizState.selectedOption} className="cg-btn cg-btn-outline" style={{backgroundColor: quizState.selectedOption ? '#3B82F6' : 'transparent', color: quizState.selectedOption ? '#FFF' : '', borderColor: quizState.selectedOption ? '#3B82F6' : '#475569'}}>
                Submit Answer
              </button>
            ) : (
              <button onClick={nextQuestion} className="cg-btn cg-btn-primary">
                {quizState.currentQIndex < quizState.quizData.length - 1 ? "Next Question →" : "Complete Assessment →"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}