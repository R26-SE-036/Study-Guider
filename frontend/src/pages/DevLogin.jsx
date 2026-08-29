import { useState } from 'react';

import { login, register, saveTokens } from '../lib/codeguru-auth.js';
import { CLIENT_NAME, CODE_COACH_URL } from '../lib/config.js';

/**
 * Localhost-only sign in.
 *
 * Same fields and same calls as the shared Code Guru portal — it posts to the
 * same Code Coach endpoints and stores the same tokens. The only difference is
 * that it is served from here, so you can work on Study Guider without running
 * the portal alongside it.
 *
 * App.jsx only renders this when devLoginEnabled() passes, which needs BOTH a
 * localhost hostname and VITE_ENABLE_DEV_LOGIN. A deployed build sends
 * students to the portal instead.
 */
export default function DevLogin({ onSignedIn }) {
  const [registering, setRegistering] = useState(false);
  const [fullName, setFullName] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setBusy(true);

    try {
      const auth = registering
        ? await register(CODE_COACH_URL, {
            fullName: fullName.trim(),
            email: identifier.trim(),
            password,
            clientName: CLIENT_NAME,
          })
        : await login(CODE_COACH_URL, {
            identifier: identifier.trim(),
            password,
            clientName: CLIENT_NAME,
          });

      saveTokens(auth);
      onSignedIn(auth.user);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const inputStyle = {
    width: '100%',
    padding: '12px 14px',
    marginBottom: '4px',
    borderRadius: '10px',
    border: '1px solid rgba(255,255,255,0.12)',
    background: 'rgba(15, 23, 42, 0.6)',
    color: '#F8FAFC',
    fontSize: '0.95rem',
  };

  const labelStyle = {
    display: 'block',
    fontSize: '0.8rem',
    color: '#94A3B8',
    marginTop: '16px',
    marginBottom: '6px',
    fontWeight: 600,
  };

  return (
    <div className="cg-card fadeIn cg-glass-panel" style={{ maxWidth: '440px', margin: '60px auto', padding: '40px' }}>
      <div
        style={{
          padding: '8px 12px',
          borderRadius: '8px',
          background: 'rgba(245, 158, 11, 0.12)',
          color: '#FCD34D',
          fontSize: '0.78rem',
          fontWeight: 600,
          marginBottom: '24px',
        }}
      >
        Localhost only — the deployed platform uses the shared Code Guru portal
      </div>

      <h2 className="cg-title-section" style={{ fontSize: '1.7rem', marginBottom: '6px' }}>
        {registering ? 'Create a test account' : 'Sign in'}
      </h2>
      <p className="cg-text-muted" style={{ fontSize: '0.85rem', marginBottom: '10px' }}>
        Signing in to Code Coach at {CODE_COACH_URL}
      </p>

      <form onSubmit={handleSubmit} noValidate>
        {error && (
          <div
            style={{
              padding: '10px 12px',
              borderRadius: '8px',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#FCA5A5',
              fontSize: '0.85rem',
              marginTop: '18px',
            }}
          >
            {error}
          </div>
        )}

        {registering && (
          <>
            <label style={labelStyle} htmlFor="dev_full_name">Full name</label>
            <input
              id="dev_full_name"
              name="full_name"
              type="text"
              required
              style={inputStyle}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Student"
            />
          </>
        )}

        <label style={labelStyle} htmlFor="dev_identifier">
          {registering ? 'Email address' : 'Email or username'}
        </label>
        <input
          id="dev_identifier"
          name={registering ? 'email' : 'identifier'}
          type="text"
          autoComplete="username"
          required
          style={inputStyle}
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder="student@example.com"
        />

        <label style={labelStyle} htmlFor="dev_password">Password</label>
        <input
          id="dev_password"
          name="password"
          type="password"
          autoComplete={registering ? 'new-password' : 'current-password'}
          required
          style={inputStyle}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          type="submit"
          disabled={busy}
          className="cg-btn cg-btn-premium-success"
          style={{ width: '100%', marginTop: '28px', padding: '14px' }}
        >
          {busy ? 'Working…' : registering ? 'Create account' : 'Sign in'}
        </button>
      </form>

      <button
        type="button"
        onClick={() => { setRegistering(!registering); setError(''); }}
        style={{
          background: 'none',
          border: 'none',
          color: '#60A5FA',
          fontSize: '0.85rem',
          cursor: 'pointer',
          marginTop: '20px',
          padding: 0,
        }}
      >
        {registering ? 'I already have an account' : 'I need a new test account'}
      </button>
    </div>
  );
}
