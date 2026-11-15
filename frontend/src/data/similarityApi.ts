import { useEffect, useRef, useState } from 'react';
import { errorMessage, requestKey, type SearchRequest, type SearchResponse } from '../domain/similarity';

export const SEARCH_TIMEOUT_MS = 30_000;
export const DEBOUNCE_MS = 300;

export class SearchTimeout extends Error {}

export async function postSearch(request: SearchRequest, signal: AbortSignal): Promise<SearchResponse> {
  const response = await fetch('/api/similarity/search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(errorMessage(body.detail, response.status));
  }
  try { return await response.json(); }
  catch { throw new Error('La respuesta no tiene el formato esperado. Vuelve a intentarlo.'); }
}

type Settled = { key: string; attempt: number; data?: SearchResponse; error?: string };

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
        else if (!controller.signal.aborted) setSettled({ key, attempt, error: error.message });
      }).finally(() => clearTimeout(limit));
    }, debounceMs);
    return () => { clearTimeout(delay); clearTimeout(limit); controller.abort(); };
    // `request` is represented by `key`: an equal request must not restart the search.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt, debounceMs]);
  const current = settled?.key === key && settled.attempt === attempt ? settled : null;
  const loading = !!request && !current;
  return {
    data: current?.data ?? (loading ? lastGood.current : undefined), error: current?.error, loading,
    stale: loading && !!lastGood.current, retry: () => setAttempt(n => n + 1),
  };
}
