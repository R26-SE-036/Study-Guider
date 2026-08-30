/**
 * Study Guider's environment, in one place.
 *
 * codeguru-auth.js takes its configuration as arguments so it can stay
 * identical to the master copy in the code-coach repo. This module is the
 * Vite-specific half that feeds it.
 */

/** Study Guider's own backend. */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8010';

/** Code Coach — the platform's identity provider. Refreshes go here. */
export const CODE_COACH_URL =
  import.meta.env.VITE_CODE_COACH_URL || 'http://127.0.0.1:8000';

/** The shared login UI. Students with no session are sent here. */
export const PORTAL_URL = import.meta.env.VITE_PORTAL_URL || 'http://localhost:4200';

/** Enables /dev-login. Ignored unless the page is served from localhost. */
export const DEV_LOGIN_FLAG = import.meta.env.VITE_ENABLE_DEV_LOGIN;

export const CLIENT_NAME = 'codeguru-study-guider';
