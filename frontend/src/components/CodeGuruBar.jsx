/**
 * The Code Guru platform bar.
 *
 * MASTER COPY. Lives in code-coach/portal/src/components/ and is COPIED into
 * Study Guider and the Gamification Engine; PairPath keeps a hand-transcribed
 * .tsx twin because it is a Next/TypeScript app. Do not edit a copy - edit this
 * file and run code-coach/sync-codeguru-shared.sh.
 *
 * ---------------------------------------------------------------------------
 * Why the links go through the portal
 * ---------------------------------------------------------------------------
 * The four services run on four different origins, so a plain <a> to a sibling
 * would land there with no session - localStorage does not cross origins. Every
 * service link therefore points at {portal}/go?to=<key>, and the portal does
 * the token handoff it already does from the Home page, including the
 * redirect_uri allow-list check.
 *
 * That also means a sibling never has to be told its siblings' URLs. Only the
 * portal holds the service registry, and adding a fifth service is a change in
 * one repo rather than four.
 *
 * All styling lives in codeguru-theme.css (the `.cg-bar-*` rules), so the four
 * copies of this markup cannot drift apart visually.
 */
import React from 'react';

/** Service keys the portal's /go route understands. */
export const CG_SERVICES = [
  { key: 'home', label: 'Home' },
  { key: 'study-guider', label: 'Study Guider' },
  { key: 'pairpath', label: 'PairPath' },
  { key: 'gamification', label: 'Games' },
];

/** "Jane Student" -> "JS"; falls back to the email, then to a neutral glyph. */
export function cgInitials(user) {
  const name = user?.full_name || user?.fullName || user?.email || '';
  const parts = String(name).trim().split(/[\s@._-]+/).filter(Boolean);
  if (!parts.length) return '·';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function CodeGuruBar({ service, portalUrl, user, onSignOut }) {
  const base = String(portalUrl || '').replace(/\/+$/, '');
  const displayName = user?.full_name || user?.fullName || user?.email || '';
  const current = CG_SERVICES.find((s) => s.key === service);

  function hrefFor(key) {
    if (key === 'home') return base + '/';
    // The service you are already in links to its own root, so the current tab
    // is a cheap in-app navigation rather than a round trip through the portal.
    if (key === service) return '/';
    return base + '/go?to=' + encodeURIComponent(key);
  }

  return (
    <header className="cg-bar">
      <div className="cg-bar-inner">
        <a className="cg-bar-brand" href={base + '/'}>
          <span className="cg-bar-mark" aria-hidden="true">CG</span>
          <span className="cg-bar-titles">
            <span className="cg-bar-title">Code Guru</span>
            {current && <span className="cg-bar-service">{current.label}</span>}
          </span>
        </a>

        <nav className="cg-bar-nav" aria-label="Code Guru services">
          {CG_SERVICES.map((s) => (
            <a
              key={s.key}
              className="cg-bar-link"
              href={hrefFor(s.key)}
              aria-current={s.key === service ? 'page' : undefined}
            >
              {s.label}
            </a>
          ))}
        </nav>

        {user && (
          <div className="cg-bar-user">
            <span className="cg-bar-avatar" aria-hidden="true">{cgInitials(user)}</span>
            <span className="cg-bar-username" title={displayName}>{displayName}</span>
            {onSignOut && (
              <button type="button" className="cg-bar-signout" onClick={onSignOut}>
                Sign out
              </button>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
