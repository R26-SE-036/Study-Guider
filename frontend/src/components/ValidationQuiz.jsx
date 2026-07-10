import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function ValidationQuiz({ studentId, errorType, codeSnippet }) {
  const [quizData, setQuizData] = useState(null);
  const [quizLoading, setQuizLoading] = useState(true);
  const [currentQIndex, setCurrentQIndex] = useState(0);
  const [selectedOption, setSelectedOption] = useState(null);
  const [isAnswerChecked, setIsAnswerChecked] = useState(false);
  const [score, setScore] = useState(0);
  const [quizFinished, setQuizFinished] = useState(false);
  const [graphStatus, setGraphStatus] = useState("pending"); 

  useEffect(() => {
    const payload = { student_id: studentId, error_type: errorType, code_snippet: codeSnippet };
    axios.post(`${API_BASE_URL}/api/quiz/generate`, payload)
      .then(response => {
        if (response.data.quiz_data && response.data.quiz_data.length > 0) {
          setQuizData(response.data.quiz_data);
        }
        setQuizLoading(false);
      })
      .catch(error => {
        console.error("Quiz Error:", error);
        setQuizLoading(false);
      });
  }, [studentId, errorType, codeSnippet]);

  const checkAnswer = () => {
    setIsAnswerChecked(true);
    if (selectedOption === quizData[currentQIndex]?.correct_answer) {
      setScore(score + 1);
    }
  };

  const handleQuizCompletion = () => {
    setQuizFinished(true);
    setGraphStatus("updating");

    const payload = { 
        student_id: studentId, 
        concept: errorType, 
        score: score, 
        total_questions: quizData.length 
    };

    axios.post(`${API_BASE_URL}/api/progress/update`, payload)
      .then(response => { setGraphStatus(response.data.success ? "success" : "error"); })
      .catch(error => { console.error("Neo4j Update Error:", error); setGraphStatus("error"); });
  };

  const nextQuestion = () => {
    if (currentQIndex < quizData.length - 1) {
      setCurrentQIndex(currentQIndex + 1);
      setSelectedOption(null);
      setIsAnswerChecked(false);
    } else {
      handleQuizCompletion();
    }
  };

  if (quizFinished) {
    const passed = score >= (quizData?.length / 2);
    return (
      <div className="cg-card ValidationQuiz fadeIn" style={{ textAlign: 'center', padding: '50px 30px' }}>
        <h2 className="cg-title-section" style={{ fontSize: '2rem' }}>Assessment Complete</h2>
        <div style={{ margin: '30px 0' }}>
          <span className="cg-text-muted" style={{ fontSize: '1.2rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Final Score</span>
          <h1 style={{ fontSize: '4rem', margin: '10px 0', color: passed ? '#34D399' : '#F87171' }}>
            {score}<span style={{color: '#475569'}}>/</span>{quizData?.length || 4}
          </h1>
        </div>

        <div style={{ marginTop: '40px', paddingTop: '30px', borderTop: '1px solid #334155', textAlign: 'left' }}>
          <h4 className="cg-title-content">Database Sync Status</h4>
          {graphStatus === "updating" && <div className="cg-feedback-box" style={{backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#FBBF24'}}>⏳ Committing results to Neo4j Knowledge Graph...</div>}
          {graphStatus === "success" && <div className="cg-feedback-box cg-feedback-success">✅ Neo4j Database Sync Successful! Relationship updated.</div>}
          {graphStatus === "error" && <div className="cg-feedback-box cg-feedback-error">❌ Database Connection Failed. Please check Backend Neo4j configurations.</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="cg-card ValidationQuiz fadeIn">
      {quizLoading || !quizData ? (
        <div style={{ textAlign: 'center', padding: '60px 0' }}>
          <h3 className="cg-title-section" style={{ color: '#3B82F6' }}>Generating AI Assessment...</h3>
          <p className="cg-text-muted">Analyzing your code context to build relevant questions.</p>
        </div>
      ) : (
        <div>
          <div className="cg-flex-between" style={{ marginBottom: '30px' }}>
            <span className="cg-text-muted" style={{fontFamily: 'Fira Code', fontSize: '0.9rem'}}>QUESTION {currentQIndex + 1}/{quizData.length}</span>
            <span style={{ padding: '4px 10px', backgroundColor: '#0F172A', borderRadius: '4px', fontSize: '0.8rem', color: '#94A3B8', border: '1px solid #334155' }}>{errorType}</span>
          </div>
          
          <h3 className="cg-title-section" style={{ fontSize: '1.3rem', marginBottom: '30px', lineHeight: '1.5' }}>
            {quizData[currentQIndex]?.question}
          </h3>
          
          <div className="cg-flex-col" style={{ gap: '15px', marginBottom: '30px' }}>
            {quizData[currentQIndex]?.options?.map((option, idx) => (
              <button 
                key={idx}
                onClick={() => !isAnswerChecked && setSelectedOption(option)}
                disabled={isAnswerChecked}
                className={`cg-quiz-option ${selectedOption === option ? 'selected' : ''}`}
              >
                {option}
              </button>
            ))}
          </div>

          {isAnswerChecked && (
            <div className={`cg-feedback-box ${selectedOption === quizData[currentQIndex]?.correct_answer ? 'cg-feedback-success' : 'cg-feedback-error'}`}>
              <h4 style={{ margin: '0 0 8px 0', color: selectedOption === quizData[currentQIndex]?.correct_answer ? '#34D399' : '#F87171' }}>
                {selectedOption === quizData[currentQIndex]?.correct_answer ? "Correct" : "Incorrect"}
              </h4>
              <p style={{ margin: 0, color: '#E2E8F0' }}>{quizData[currentQIndex]?.explanation}</p>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
            {!isAnswerChecked ? (
              <button onClick={checkAnswer} disabled={!selectedOption} className="cg-btn cg-btn-outline" style={{backgroundColor: selectedOption ? '#3B82F6' : 'transparent', color: selectedOption ? '#FFF' : '', borderColor: selectedOption ? '#3B82F6' : '#475569'}}>
                Submit Answer
              </button>
            ) : (
              <button onClick={nextQuestion} className="cg-btn cg-btn-primary">
                {currentQIndex < quizData.length - 1 ? "Next Question →" : "Complete Assessment →"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}