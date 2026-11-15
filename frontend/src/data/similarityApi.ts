import { useEffect, useRef, useState } from 'react';
import { errorMessage, requestKey, type ReferenceCatalog, type SearchRequest, type SearchResponse } from '../domain/similarity';

export const SEARCH_TIMEOUT_MS = 30_000;
export const DEBOUNCE_MS = 300;

export class SearchTimeout extends Error {}
/** The server has no engine (503) or cannot be reached: the rest of the app keeps working. */
export class SearchUnavailable extends Error {}

async function call(url: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try { response = await fetch(url, init); }
  catch (error) {
    if (init.signal?.aborted) throw error;
    throw new SearchUnavailable('No hay conexión con el motor de búsqueda.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = errorMessage(body.detail, response.status);
    throw response.status === 503 ? new SearchUnavailable(message) : new Error(message);
  }
  return response;
}

export async function postSearch(request: SearchRequest, signal: AbortSignal): Promise<SearchResponse> {
  const response = await call('/api/similarity/search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal,
  });
  try { return await response.json(); }
  catch { throw new Error('La respuesta no tiene el formato esperado. Vuelve a intentarlo.'); }
}

export async function getReferences(signal: AbortSignal): Promise<ReferenceCatalog> {
  const response = await call('/api/similarity/references', { signal });
  try { return await response.json(); }
  catch { throw new Error('El catálogo de referencias no tiene el formato esperado.'); }
}

/** The reference catalog (`GET /api/similarity/references`), loaded once per mount. */
export function useReferenceCatalog() {
  const [result, setResult] = useState<{ data?: ReferenceCatalog; error?: string; unavailable?: boolean }>({});
  useEffect(() => {
    const controller = new AbortController();
    getReferences(controller.signal)
      .then(data => { if (!controller.signal.aborted) setResult({ data }); })
      .catch(error => { if (!controller.signal.aborted) setResult({ error: error.message, unavailable: error instanceof SearchUnavailable }); });
    return () => controller.abort();
  }, []);
  return result;
}

type Settled = { key: string; attempt: number; data?: SearchResponse; error?: string; unavailable?: boolean };

/**
 * One live request at a time: a new request (after a short debounce) aborts the previous one, so an old
 * answer never appears under new controls. The last good answer stays available as `data` while the
 * next one loads, flagged `stale`, so the table does not flash empty on every slider move.
 */
export function useSimilaritySearch(request: SearchRequest | null, debounceMs = DEBOUNCE_MS) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const lastGood = useRef<SearchResponse | undefined>(undefined);
  const key = request ? requestKey(request) : null;
  useEffect(() => {
    if (!request || key === null) return;
    const controller = new AbortController();
    let timedOut = false;
    const limit = setTimeout(() => { timedOut = true; controller.abort(); }, SEARCH_TIMEOUT_MS);
    const delay = setTimeout(() => {
      postSearch(request, controller.signal).then(data => {
        if (controller.signal.aborted) return;
        lastGood.current = data;
        setSettled({ key, attempt, data });
      }).catch(error => {
        if (timedOut) setSettled({ key, attempt, error: 'La búsqueda tardó más de 30 s. Inténtalo de nuevo.' });
        else if (!controller.signal.aborted) setSettled({ key, attempt, error: error.message, unavailable: error instanceof SearchUnavailable });
      }).finally(() => clearTimeout(limit));
    }, debounceMs);
    return () => { clearTimeout(delay); clearTimeout(limit); controller.abort(); };
    // `request` is represented by `key`: an equal request must not restart the search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt, debounceMs]);
  const current = settled?.key === key && settled.attempt === attempt ? settled : null;
  const loading = !!request && !current;
  return {
    data: current?.data ?? (loading ? lastGood.current : undefined), error: current?.error,
    unavailable: !!current?.unavailable, loading,
    stale: loading && !!lastGood.current, retry: () => setAttempt(n => n + 1),
  };
}
