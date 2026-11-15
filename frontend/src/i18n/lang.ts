/**
 * Active interface language, readable outside React (formatters, fetch helpers, Cesium labels).
 * Pure module: no browser globals at import time, so the Node tests can load modules that use it.
 * `I18nProvider` keeps it in sync with the React state.
 */
export type Lang = 'es' | 'en';
export const LANGS: readonly Lang[] = ['es', 'en'];
/** A text in both languages: Spanish first, English second. */
export type Msg = readonly [es: string, en: string];

let current: Lang = 'es';
export const getLang = (): Lang => current;
export function setCurrentLang(lang: Lang) { current = lang; }
/** Text in the active language. */
export const tr = (es: string, en: string): string => (current === 'en' ? en : es);
/** A stored bilingual message, rendered in the active language. */
export const msg = (m: Msg | string): string => (typeof m === 'string' ? m : tr(m[0], m[1]));
export const isLang = (value: unknown): value is Lang => value === 'es' || value === 'en';

/**
 * Engine warnings arrive in Spanish with a fixed shape («Vista espectral con peso 0.1 excluida:
 * not_fitted»). In English, translate the known shape and keep any other text unchanged.
 */
const VIEW_EN: Record<string, string> = {
  escabrosidad: 'ruggedness', forma_hipsometrica: 'hypsometric shape', organizacion: 'organisation',
  regimen_morfologico: 'morphological regime', espectral: 'spectral', termica: 'thermal', radar: 'radar',
  entorno_superficial: 'surface setting', emisividad_cmg: 'emissivity',
};
export function warningText(text: string, lang: Lang = current): string {
  if (lang !== 'en') return text;
  const m = /^Vista (\S+) con peso ([\d.]+) excluida: (\S+)$/.exec(text);
  return m ? `The ${VIEW_EN[m[1]] ?? m[1]} view (weight ${m[2]}) was excluded: ${m[3]}` : text;
}

/** A label table whose values follow the active language (`labels[key]` reads it on access). */
export function localized<K extends string>(map: Record<K, Msg>): Record<K, string> {
  const out = {} as Record<K, string>;
  for (const key of Object.keys(map) as K[]) Object.defineProperty(out, key, { get: () => msg(map[key]), enumerable: true });
  return out;
}
