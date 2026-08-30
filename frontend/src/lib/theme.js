/**
 * Read Code Guru design tokens as real colour strings.
 *
 * Why this exists: most of the app can hand `var(--cg-accent)` straight to CSS,
 * but Recharts passes colours through to SVG *presentation attributes*
 * (`stroke`, `fill`, `stopColor`), and browsers do not resolve `var()` inside
 * an attribute value - the element simply renders with no colour. So anything
 * heading for an SVG attribute has to be resolved to a concrete value first.
 *
 * `useThemeColors` re-reads on `codeguru:themechange`, so when the light/dark
 * toggle lands the charts follow it without any further change here.
 */
import { useEffect, useState } from 'react';

/** One token's computed value, e.g. cssVar('--cg-accent') -> 'rgb(37, 99, 235)'. */
export function cssVar(name, fallback = '') {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name);
  return value.trim() || fallback;
}

/**
 * Resolve a map of { key: '--cg-token' } to { key: 'rgb(...)' }.
 *
 * Pass a module-level constant as `tokens` - a fresh object literal on every
 * render would re-run the effect forever.
 */
export function useThemeColors(tokens) {
  const read = () =>
    Object.fromEntries(Object.entries(tokens).map(([key, name]) => [key, cssVar(name)]));

  const [colors, setColors] = useState(read);

  useEffect(() => {
    const refresh = () => setColors(read());
    // Fires once after mount so the first paint picks up the stylesheet even
    // if it resolved after the initial render.
    refresh();
    window.addEventListener('codeguru:themechange', refresh);
    return () => window.removeEventListener('codeguru:themechange', refresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tokens]);

  return colors;
}
