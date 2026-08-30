/**
 * The axios instance every component uses to reach Study Guider's backend.
 *
 * It exists so the platform token is attached in exactly one place. Components
 * used to build their own axios calls against a bare API_BASE_URL and pass a
 * `student_id` in the body; the backend now takes the student from the token,
 * so a request without the header simply gets a 401.
 */

import axios from 'axios';

import { API_BASE_URL, CODE_COACH_URL, PORTAL_URL } from './config.js';
import {
  clearTokens,
  loadTokens,
  refresh,
  redirectToPortal,
  saveTokens,
} from './codeguru-auth.js';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const { accessToken } = loadTokens();
  if (accessToken) {
    config.headers.Authorization = 'Bearer ' + accessToken;
  }
  return config;
});

/**
 * On 401: rotate the access token once and replay the request.
 *
 * Access tokens live one hour, so a student who leaves a lesson open over
 * lunch comes back to a dead token. Refreshing here means they never see it.
 * The `_retried` flag caps this at one attempt — a genuinely revoked session
 * would otherwise refresh-and-retry forever.
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const { refreshToken } = loadTokens();

    if (error.response?.status !== 401 || original?._retried || !refreshToken) {
      if (error.response?.status === 401) {
        clearTokens();
        redirectToPortal(PORTAL_URL);
      }
      return Promise.reject(error);
    }

    original._retried = true;

    try {
      const refreshed = await refresh(CODE_COACH_URL, refreshToken);
      saveTokens(refreshed);
      original.headers.Authorization = 'Bearer ' + refreshed.tokens.access_token;
      return api(original);
    } catch {
      clearTokens();
      redirectToPortal(PORTAL_URL);
      return Promise.reject(error);
    }
  },
);

export default api;
