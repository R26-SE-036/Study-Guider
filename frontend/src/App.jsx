import { useCallback, useEffect, useState } from 'react';

import TriggerCard from './components/TriggerCard';
import MicroLesson from './components/MicroLesson';
import ValidationQuiz from './components/ValidationQuiz';
import StudentDashboard from './components/StudentDashboard';
import DevLogin from './pages/DevLogin';
import CodeGuruBar from './components/CodeGuruBar';

import api from './lib/api';
import {
  clearTokens,
  consumeHandoffFragment,
  devLoginEnabled,
  isSignedIn,
  loadTokens,
  loadUser,
  logout,
  redirectToPortal,
} from './lib/codeguru-auth';
import { CODE_COACH_URL, DEV_LOGIN_FLAG, PORTAL_URL } from './lib/config';
import './App.css';

/**
 * Study Guider.
 *
 * What changed, and why it matters: this component used to hardcode the
 * student (`user_0bcc693e70f0`), the error type, the concept, the code and the
 * error count. It demonstrated the UI but was not connected to anything.
 *
 * Now the student comes from the signed-in session, and the work to do comes
 * from Code Coach's remediation triggers — raised while the student actually
 * struggles in the VS Code extension. Opening a lesson and finishing a quiz
 * are reported back, which is what marks a trigger resolved.
 */
function App() {
  // 'checking' until we know whether there is a session, so we never flash the
  // signed-out UI at someone who is signed in.
  const [authState, setAuthState] = useState('checking');
  const [user, setUser] = useState(null);

  const [triggers, setTriggers] = useState([]);
  const [activeTrigger, setActiveTrigger] = useState(null);
  const [lessonData, setLessonData] = useState(null);
  const [cognitiveState, setCognitiveState] = useState('High Cognitive Load');

  const [phase, setPhase] = useState('triggers');
  const [loadingTriggers, setLoadingTriggers] = useState(false);
  const [buildingLesson, setBuildingLesson] = useState(null);
  const [error, setError] = useState('');

  const canDevLogin = devLoginEnabled(DEV_LOGIN_FLAG);

  // ── Session ──

  useEffect(() => {
    // Arriving from the portal? The tokens are in the URL fragment. This also
    // scrubs them from the address bar.
    consumeHandoffFragment();

    if (isSignedIn()) {
      setUser(loadUser());
      setAuthState('signed-in');
      return;
    }

    // No session. On localhost with the flag set, sign in right here;
    // otherwise the shared portal is the only login surface.
    if (canDevLogin) {
      setAuthState('signed-out');
    } else {
      redirectToPortal(PORTAL_URL);
    }
  }, [canDevLogin]);

  const loadTriggers = useCallback(() => {
    setLoadingTriggers(true);
    setError('');

    api
      .get('/api/remediation/triggers')
      .then((response) => setTriggers(response.data.triggers || []))
      .catch((err) => {
        // A 401 is already handled by the interceptor (it redirects to login),
        // so anything reaching here is a real failure worth showing.
        if (err.response?.status !== 401) {
          setError(
            err.response?.data?.detail ||
              'Could not reach Code Coach to load your struggle triggers.',
          );
        }
      })
      .finally(() => setLoadingTriggers(false));
  }, []);

  useEffect(() => {
    if (authState === 'signed-in') loadTriggers();
  }, [authState, loadTriggers]);

  async function handleSignOut() {
    const { accessToken } = loadTokens();
    if (accessToken) await logout(CODE_COACH_URL, accessToken);
    clearTokens();
    if (canDevLogin) {
      setAuthState('signed-out');
      setUser(null);
      setTriggers([]);
      setPhase('triggers');
    } else {
      redirectToPortal(PORTAL_URL);
    }
  }

  // ── Remediation ──

  /**
   * Build the micro-lesson for one trigger, and tell Code Coach it was opened.
   *
   * The `lesson-opened` call is what moves the trigger off `pending`, so the
   * student is not nagged about the same concept while working through it. It
   * is deliberately not blocking: a lesson that generated fine should still be
   * shown even if the bookkeeping call fails.
   */
  function openLesson(trigger) {
    setBuildingLesson(trigger.trigger_id);
    setError('');

    api
      .post('/api/struggle/detect', {
        trigger_id: trigger.trigger_id,
        learning_session_id: trigger.learning_session_id,
        error_type: trigger.error_type,
        concept_tag: trigger.concept_tag,
        // The real count behind the trigger, from Code Coach.
        error_count: trigger.repeat_count ?? 3,
      })
      .then((response) => {
        const content = response.data.lesson_content;
        if (!content) {
          setError('Code Guru did not consider this a struggle worth a lesson.');
          return;
        }

        setLessonData({
          title: response.data.lesson_title || trigger.lesson?.title || 'Mastering the Concept',
          issue: content.issue,
          explanation: content.explanation,
          hint: content.hint,
          exampleCode: content.exampleCode,
          videoUrl: content.videoUrl,
          referenceLink: content.referenceLink,
          mermaidDiagram: content.mermaidDiagram,
          // The snippet is an illustration of this mistake, not the student's
          // own code — Code Coach never stores the source, only a hash of it.
          studentCode: response.data.code_snippet,
          exampleIsGeneric: response.data.example_is_generic,
        });

        if (response.data.cognitive_state) setCognitiveState(response.data.cognitive_state);
        setActiveTrigger(trigger);
        setPhase('lesson');

        api
          .post(`/api/remediation/triggers/${trigger.trigger_id}/lesson-opened`, {
            lesson_id: trigger.lesson?.lesson_id || 'lesson_general_01',
          })
          .catch((err) => console.error('Could not report lesson-opened:', err));
      })
      .catch((err) => {
        if (err.response?.status !== 401) {
          setError(err.response?.data?.detail || 'Could not build the lesson. Please try again.');
        }
      })
      .finally(() => setBuildingLesson(null));
  }

  /** The quiz finished. Reporting the score is what closes the loop. */
  function handleQuizComplete() {
    setActiveTrigger(null);
    setLessonData(null);
    setPhase('triggers');
    loadTriggers();
  }

  function goHome() {
    setPhase('triggers');
    setActiveTrigger(null);
    setLessonData(null);
    loadTriggers();
  }

  // ── Render ──

  if (authState === 'checking') {
    return (
      <div className="App-container">
        <div style={{ textAlign: 'center', padding: '120px 20px' }}>
          <div className="spinner" style={{ fontSize: '2.5rem' }}>🔐</div>
          <p className="cg-text-muted" style={{ marginTop: '16px' }}>Checking your session…</p>
        </div>
      </div>
    );
  }

  if (authState === 'signed-out') {
    return (
      <div className="App-container">
        <DevLogin
          onSignedIn={(signedInUser) => {
            setUser(signedInUser);
            setAuthState('signed-in');
          }}
        />
      </div>
    );
  }

  return (
    <>
      <CodeGuruBar
        service="study-guider"
        portalUrl={PORTAL_URL}
        user={user}
        onSignOut={handleSignOut}
      />
    <div className="App-container">
      <header className="cg-header cg-flex-between">
        <div>
          <h1 className="cg-title-main">Study Guider</h1>
          <p className="cg-subtitle">
            Micro-lessons and quizzes for the concepts Code Coach sees you struggling with.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          {phase !== 'dashboard' && (
            <button onClick={() => setPhase('dashboard')} className="cg-btn cg-btn-outline">
              <span style={{ marginRight: '8px' }}>📊</span> Analytics
            </button>
          )}
        </div>
      </header>

      <div className="cg-content-wrapper">
        {error && (
          <div
            style={{
              padding: '14px 18px',
              borderRadius: '12px',
              background: 'var(--cg-danger-soft)',
              border: '1px solid rgb(var(--cg-rgb-danger) / 0.3)',
              color: 'var(--cg-danger)',
              marginBottom: '24px',
            }}
          >
            {error}
          </div>
        )}

        {phase === 'triggers' && (
          <>
            {loadingTriggers && (
              <div style={{ textAlign: 'center', padding: '80px 20px' }}>
                <div className="spinner" style={{ fontSize: '2.5rem' }}>🔎</div>
                <p className="cg-text-muted" style={{ marginTop: '16px' }}>
                  Checking Code Coach for struggle patterns…
                </p>
              </div>
            )}

            {!loadingTriggers && triggers.length === 0 && (
              <div className="cg-card fadeIn cg-glass-panel" style={{ textAlign: 'center', padding: '70px 40px' }}>
                <div style={{ fontSize: '3.5rem', marginBottom: '18px' }}>✅</div>
                <h2 className="cg-title-section" style={{ fontSize: '1.9rem', marginBottom: '12px' }}>
                  Nothing to work on right now
                </h2>
                <p className="cg-text-muted" style={{ maxWidth: '520px', margin: '0 auto', lineHeight: 1.65 }}>
                  Code Coach has not flagged any repeated struggles for you. Keep coding in VS Code —
                  when the same mistake keeps coming back, a lesson will appear here.
                </p>
                <button onClick={loadTriggers} className="cg-btn cg-btn-outline" style={{ marginTop: '28px' }}>
                  Check again
                </button>
              </div>
            )}

            {!loadingTriggers &&
              triggers.map((trigger) => (
                <TriggerCard
                  key={trigger.trigger_id}
                  trigger={trigger}
                  loading={buildingLesson === trigger.trigger_id}
                  onGenerateLesson={() => openLesson(trigger)}
                />
              ))}
          </>
        )}

        {phase === 'lesson' && lessonData && (
          <MicroLesson
            lessonData={lessonData}
            studentCode={lessonData.studentCode}
            cognitiveState={cognitiveState}
            onStartQuiz={() => setPhase('quiz')}
          />
        )}

        {phase === 'quiz' && activeTrigger && (
          <ValidationQuiz
            trigger={activeTrigger}
            errorType={activeTrigger.error_type}
            onComplete={handleQuizComplete}
          />
        )}

        {phase === 'dashboard' && (
          <StudentDashboard cognitiveState={cognitiveState} onBack={goHome} />
        )}
      </div>
    </div>
    </>
  );
}

export default App;
