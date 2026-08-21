import { useState, useEffect } from 'react';
import axios from 'axios';
import TriggerCard from './components/TriggerCard';
import MicroLesson from './components/MicroLesson';
import ValidationQuiz from './components/ValidationQuiz';
import StudentDashboard from './components/StudentDashboard';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function App() {
  // 🚀 State from localStorage to survive reloads
  const [currentPhase, setCurrentPhase] = useState(() => {
    return localStorage.getItem('cg_currentPhase') || "trigger";
  });
  
  const [lessonData, setLessonData] = useState(() => {
    const savedLesson = localStorage.getItem('cg_lessonData');
    return savedLesson ? JSON.parse(savedLesson) : null;
  });

  const [cognitiveState, setCognitiveState] = useState(() => {
    return localStorage.getItem('cg_cognitiveState') || "High Cognitive Load";
  });
  
  const [loading, setLoading] = useState(false);

  const studentId = "user_0bcc693e70f0";
  const errorType = "ARRAY_LENGTH_INDEX_MISUSE";
  const conceptTag = "arrays";
  const codeSnippet = "int[] arr = new int[5]; arr[5] = 10;"; 
  const errorCount = 4; 

  // 🚀 Save state to localStorage whenever changed
  useEffect(() => {
    localStorage.setItem('cg_currentPhase', currentPhase);
  }, [currentPhase]);

  useEffect(() => {
    if (lessonData) {
      localStorage.setItem('cg_lessonData', JSON.stringify(lessonData));
    } else {
      localStorage.removeItem('cg_lessonData');
    }
  }, [lessonData]);

  useEffect(() => {
    localStorage.setItem('cg_cognitiveState', cognitiveState);
  }, [cognitiveState]);

  const generatePersonalizedLesson = () => {
    setLoading(true);
    const errorPayload = { 
      student_id: studentId, 
      error_type: errorType, 
      error_count: errorCount, 
      concept_tag: conceptTag,
      code_snippet: codeSnippet 
    };

    axios.post(`${API_BASE_URL}/api/struggle/detect`, errorPayload)
      .then(response => {
        if (response.data.lesson_content) {
          setLessonData({
            title: response.data.lesson_title || "Mastering the Concept",
            issue: response.data.lesson_content.issue,
            explanation: response.data.lesson_content.explanation,
            hint: response.data.lesson_content.hint,
            exampleCode: response.data.lesson_content.exampleCode,
            videoUrl: response.data.lesson_content.videoUrl, 
            referenceLink: response.data.lesson_content.referenceLink,
            mermaidDiagram: response.data.lesson_content.mermaidDiagram
          });
          if (response.data.cognitive_state) {
            setCognitiveState(response.data.cognitive_state);
          }
          setCurrentPhase("lesson");
        }
        setLoading(false);
      })
      .catch(error => {
        console.error("API Error:", error);
        setLoading(false);
      });
  };

  const goHome = () => {
    setCurrentPhase("trigger");
    setLessonData(null);
    // Clear all saved progress when going back to home
    localStorage.removeItem('cg_currentPhase');
    localStorage.removeItem('cg_lessonData');
    localStorage.removeItem('cg_quizState'); 
    localStorage.removeItem('cg_cognitiveState');
  };

  return (
    <div className="App-container">
      <header className="cg-header cg-flex-between">
        <div>
          <h1 className="cg-title-main">Code Guru Study Guider</h1>
          <p className="cg-subtitle">ID: <span style={{fontFamily: 'Fira Code', color: '#0066FF'}}>{studentId.substring(0, 8)}</span></p>
        </div>
        <div>
          {currentPhase !== "dashboard" && (
            <button onClick={() => setCurrentPhase("dashboard")} className="cg-btn cg-btn-outline">
              <span style={{marginRight: '8px'}}>📊</span> Analytics
            </button>
          )}
        </div>
      </header>
      <div className="cg-content-wrapper">
        {currentPhase === "trigger" && (
          <TriggerCard 
            errorType={errorType} 
            loading={loading} 
            onGenerateLesson={generatePersonalizedLesson} 
          />
        )}
        {currentPhase === "lesson" && lessonData && (
          <MicroLesson 
            lessonData={lessonData} 
            studentCode={codeSnippet}
            cognitiveState={cognitiveState}
            onStartQuiz={() => setCurrentPhase("quiz")} 
          />
        )}
        {currentPhase === "quiz" && (
          <ValidationQuiz 
            studentId={studentId} 
            errorType={errorType} 
            codeSnippet={codeSnippet} 
          />
        )}
        {currentPhase === "dashboard" && (
          <StudentDashboard 
            studentId={studentId} 
            cognitiveState={cognitiveState}
            onBack={goHome} 
          />
        )}
      </div>
    </div>
  );
}
export default App;