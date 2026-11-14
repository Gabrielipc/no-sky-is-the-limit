import { useEffect, useState } from 'react';

export async function getJSON<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'No se pudieron cargar los datos.');
  }
  try { return await response.json(); }
  catch { throw new Error('Los datos recibidos no tienen el formato esperado. Vuelve a intentarlo.'); }
}

/** Keyed responses + abort prevent an old query from appearing under new controls. */
export function useResource<T>(url: string | null) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; attempt: number; data?: T; error?: string } | null>(null);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    getJSON<T>(url, controller.signal).then(data => {
      if (!controller.signal.aborted) setResult({ key: url, attempt, data });
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ key: url, attempt, error: error.message });
    });
    return () => controller.abort();
  }, [url, attempt]);
  const current = result?.key === url && result.attempt === attempt ? result : null;
  return { data: current?.data, error: current?.error, loading: !!url && !current, retry: () => setAttempt(n => n + 1) };
}
