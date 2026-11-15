import { tr } from '../i18n/lang';
let pending: Promise<void> | null = null;

/** Production uses the copied global build; development uses Vite's lazy ESM import. */
export function loadCesium(): Promise<void> {
  if (import.meta.env.DEV) return Promise.resolve();
  if (pending) return pending;
  const base = `${import.meta.env.BASE_URL}cesium/`;
  (window as Window & { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = base;
  pending = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `${base}Cesium.js`; script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { script.remove(); pending = null; reject(new Error(tr('No se pudo cargar el visor de ubicación.', 'The location viewer could not be loaded.'))); };
    document.head.appendChild(script);
  });
  return pending;
}
